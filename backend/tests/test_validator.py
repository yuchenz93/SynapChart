"""Tests for port-type and workflow validation (core.validator + port_types v2)."""

from __future__ import annotations

import pytest

from blocks.base import PortDefinition
from core.validator import validate_connection, validate_workflow
from neurodata.port_types import Compat


def _status(out, req):
    return validate_connection(out, req)[0]


# ---------------------------------------------------------------------------
# validate_connection — three-state structural + role compatibility
# ---------------------------------------------------------------------------

class TestStructural:
    def test_exact_type_match_is_ok(self):
        status, msg = validate_connection("NeuroData[lfp]", "NeuroData[lfp]")
        assert status is Compat.OK
        assert msg == ""

    def test_container_mismatch_is_error(self):
        # str output into a NeuroData input — wrong container, hard block.
        assert _status("str", "NeuroData[lfp]") is Compat.ERROR
        assert _status("NeuroData[lfp]", "str") is Compat.ERROR

    def test_ndim_mismatch_is_error(self):
        # spike_times is 1-D; position requires 2-D.
        status, msg = validate_connection("NeuroData[spike_times]", "NeuroData[position]")
        assert status is Compat.ERROR
        assert "-D" in msg

    def test_untimed_into_timed_is_error(self):
        # tuning_curve is untimed; feeding it where a timed signal is required.
        assert _status("NeuroData[tuning_curve]", "NeuroData[lfp]") is Compat.ERROR

    def test_int_scalar_widens_to_float(self):
        assert _status("int", "float") is Compat.OK

    def test_float_scalar_does_not_narrow_to_int(self):
        assert _status("float", "int") is Compat.ERROR

    def test_any_matches_anything(self):
        assert _status("NeuroData[spike_times]", "NeuroData[any]") is Compat.OK
        assert _status("str", "NeuroData[any]") is Compat.OK   # any = true match-all
        assert _status("NeuroData[any]", "NeuroData[lfp]") is Compat.OK

    def test_str_feeds_str(self):
        assert _status("str", "str") is Compat.OK


class TestRoles:
    def test_isa_role_match_is_ok(self):
        # lfp is-a signal (raw_signal maps to role 'signal').
        assert _status("NeuroData[lfp]", "NeuroData[raw_signal]") is Compat.OK

    def test_population_tuning_curve_isa_tuning_curve(self):
        # tuning_curves_population is-a tuning_curve (structurally compatible too).
        assert _status(
            "NeuroData[tuning_curves_population]", "NeuroData[tuning_curve]"
        ) is Compat.OK

    def test_role_mismatch_same_structure_is_warn(self):
        # lfp and spike_times are both float timed arrays -> structural OK,
        # but roles differ -> soft WARN (connectable), not ERROR.
        status, msg = validate_connection("NeuroData[lfp]", "NeuroData[spike_times]")
        assert status is Compat.WARN
        assert "role" in msg.lower()

    def test_unknown_external_same_tag_is_ok(self):
        assert _status("NeuroData[custom_x]", "NeuroData[custom_x]") is Compat.OK

    def test_unknown_external_diff_tag_is_warn(self):
        # Previously silently allowed; now warns (structure is 'any', roles differ).
        assert _status("NeuroData[custom_x]", "NeuroData[custom_y]") is Compat.WARN


# ---------------------------------------------------------------------------
# validate_workflow — registry-backed graph validation
# ---------------------------------------------------------------------------

def _lfp_out():
    return [PortDefinition("out", "NeuroData[lfp]", "")]


def _lfp_in():
    return [PortDefinition("in", "NeuroData[lfp]", "")]


def _spike_in():
    return [PortDefinition("in", "NeuroData[spike_times]", "")]


def _str_in():
    return [PortDefinition("in", "str", "")]


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

    def test_structural_mismatch_reported(self, make_block):
        # A NeuroData output into a str input is a hard structural error.
        make_block("producer", lambda i, p: {"out": None}, outputs=_lfp_out())
        make_block("consumer", lambda i, p: {}, inputs=_str_in())
        wf = {
            "nodes": [_node("n1", "producer"), _node("n2", "consumer")],
            "edges": [_edge("e1", "n1", "out", "n2", "in")],
        }
        errors = validate_workflow(wf)
        assert len(errors) == 1
        assert "e1" in errors[0]

    def test_role_mismatch_is_not_a_workflow_error(self, make_block):
        # lfp -> spike_times is a role WARN (structurally fine), so the workflow
        # validator (hard errors only) must not report it.
        make_block("producer", lambda i, p: {"out": None}, outputs=_lfp_out())
        make_block("consumer", lambda i, p: {}, inputs=_spike_in())
        wf = {
            "nodes": [_node("n1", "producer"), _node("n2", "consumer")],
            "edges": [_edge("e1", "n1", "out", "n2", "in")],
        }
        assert validate_workflow(wf) == []

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
