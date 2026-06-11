"""Tests for port-type and workflow validation (core.validator)."""

from __future__ import annotations

import pytest

from blocks.base import PortDefinition
from core.validator import validate_connection, validate_workflow


# ---------------------------------------------------------------------------
# validate_connection — the compatibility table
# ---------------------------------------------------------------------------

class TestValidateConnection:
    def test_exact_type_match_is_valid(self):
        ok, msg = validate_connection("NeuroData[lfp]", "NeuroData[lfp]")
        assert ok is True
        assert msg == ""

    def test_any_accepts_compatible_source(self):
        ok, _ = validate_connection("NeuroData[spike_times]", "NeuroData[any]")
        assert ok is True

    def test_raw_signal_feeds_lfp_input(self):
        # lfp inputs accept raw_signal (a raw signal can be treated as lfp).
        ok, _ = validate_connection("NeuroData[lfp]", "NeuroData[raw_signal]")
        assert ok is True

    def test_incompatible_types_rejected(self):
        ok, msg = validate_connection("NeuroData[spike_times]", "NeuroData[position]")
        assert ok is False
        assert "mismatch" in msg.lower()

    def test_int_feeds_float(self):
        ok, _ = validate_connection("int", "float")
        assert ok is True

    def test_float_does_not_feed_int(self):
        ok, _ = validate_connection("float", "int")
        assert ok is False

    def test_population_tuning_curve_feeds_tuning_curve(self):
        # Special-cased so the population rate map can drive a single-curve decoder.
        ok, _ = validate_connection(
            "NeuroData[tuning_curves_population]", "NeuroData[tuning_curve]"
        )
        assert ok is True

    def test_unknown_external_type_is_allowed(self):
        # Types absent from the table (third-party libs) pass without checking.
        ok, _ = validate_connection("NeuroData[custom_external]", "NeuroData[whatever]")
        assert ok is True

    def test_str_only_feeds_str(self):
        assert validate_connection("str", "str")[0] is True
        assert validate_connection("str", "NeuroData[any]")[0] is False


# ---------------------------------------------------------------------------
# validate_workflow — registry-backed graph validation
# ---------------------------------------------------------------------------

def _lfp_out():
    return [PortDefinition("out", "NeuroData[lfp]", "")]


def _lfp_in():
    return [PortDefinition("in", "NeuroData[lfp]", "")]


def _spike_in():
    return [PortDefinition("in", "NeuroData[spike_times]", "")]


def _node(node_id, block_type_id):
    return {"node_id": node_id, "block_type_id": block_type_id}


def _edge(eid, s, sp, t, tp):
    return {
        "edge_id": eid,
        "source_node_id": s,
        "source_port_id": sp,
        "target_node_id": t,
        "target_port_id": tp,
    }


class TestValidateWorkflow:
    def test_valid_workflow_has_no_errors(self, make_block):
        make_block("producer", lambda i, p: {"out": None}, outputs=_lfp_out())
        make_block("consumer", lambda i, p: {}, inputs=_lfp_in())
        wf = {
            "nodes": [_node("n1", "producer"), _node("n2", "consumer")],
            "edges": [_edge("e1", "n1", "out", "n2", "in")],
        }
        assert validate_workflow(wf) == []

    def test_unregistered_block_reported(self):
        wf = {"nodes": [_node("n1", "ghost_block")], "edges": []}
        errors = validate_workflow(wf)
        assert any("not registered" in e for e in errors)

    def test_type_mismatch_reported(self, make_block):
        make_block("producer", lambda i, p: {"out": None}, outputs=_lfp_out())
        make_block("consumer", lambda i, p: {}, inputs=_spike_in())
        wf = {
            "nodes": [_node("n1", "producer"), _node("n2", "consumer")],
            "edges": [_edge("e1", "n1", "out", "n2", "in")],
        }
        errors = validate_workflow(wf)
        assert len(errors) == 1
        assert "e1" in errors[0]

    def test_missing_source_node_reported(self, make_block):
        make_block("consumer", lambda i, p: {}, inputs=_lfp_in())
        wf = {
            "nodes": [_node("n2", "consumer")],
            "edges": [_edge("e1", "ghost", "out", "n2", "in")],
        }
        errors = validate_workflow(wf)
        assert any("source node 'ghost' not found" in e for e in errors)

    def test_unknown_output_port_reported(self, make_block):
        make_block("producer", lambda i, p: {"out": None}, outputs=_lfp_out())
        make_block("consumer", lambda i, p: {}, inputs=_lfp_in())
        wf = {
            "nodes": [_node("n1", "producer"), _node("n2", "consumer")],
            "edges": [_edge("e1", "n1", "nonexistent", "n2", "in")],
        }
        errors = validate_workflow(wf)
        assert any("output port 'nonexistent'" in e for e in errors)

    def test_unknown_input_port_reported(self, make_block):
        make_block("producer", lambda i, p: {"out": None}, outputs=_lfp_out())
        make_block("consumer", lambda i, p: {}, inputs=_lfp_in())
        wf = {
            "nodes": [_node("n1", "producer"), _node("n2", "consumer")],
            "edges": [_edge("e1", "n1", "out", "n2", "nonexistent")],
        }
        errors = validate_workflow(wf)
        assert any("input port 'nonexistent'" in e for e in errors)

    def test_iterator_dynamic_output_skips_type_check(self, make_block):
        # Iterator blocks have no static output ports; their edges must not be
        # rejected for "output port not found".
        iterator = make_block("dataset_iterator", lambda i, p: {}, outputs=[])
        iterator.is_iterator = True
        make_block("consumer", lambda i, p: {}, inputs=[PortDefinition("in", "str", "")])
        wf = {
            "nodes": [_node("it", "dataset_iterator"), _node("n2", "consumer")],
            "edges": [_edge("e1", "it", "lfp_file", "n2", "in")],
        }
        assert validate_workflow(wf) == []

    def test_empty_workflow_is_valid(self):
        assert validate_workflow({"nodes": [], "edges": []}) == []
