"""Tests for the pipeline execution engine (core.executor), non-batch paths."""

from __future__ import annotations

import numpy as np
import pytest

from blocks.base import PortDefinition
from core.executor import (
    PipelineExecutor,
    _compute_source_hash,
    detect_iterator_structure,
)
from neurodata.types import NeuroData


async def _drain(agen):
    """Collect every message yielded by an async generator into a list."""
    return [msg async for msg in agen]


def _statuses(messages):
    return [m.get("status") for m in messages if m.get("status")]


def _node(node_id, bid, **params):
    return {"node_id": node_id, "block_type_id": bid, "parameters": params}


def _edge(eid, s, sp, t, tp):
    return {
        "edge_id": eid,
        "source_node_id": s,
        "source_port_id": sp,
        "target_node_id": t,
        "target_port_id": tp,
    }


# ---------------------------------------------------------------------------
# detect_iterator_structure
# ---------------------------------------------------------------------------

class TestDetectIteratorStructure:
    def test_no_iterator_returns_all_as_preloop(self):
        nodes = {"a": _node("a", "src"), "b": _node("b", "sink")}
        edges = [_edge("e", "a", "out", "b", "in")]
        it, pre, loop, collect, post = detect_iterator_structure(nodes, edges)
        assert it is None
        assert pre == ["a", "b"]
        assert loop == [] and collect == [] and post == []

    def test_iterator_splits_into_loop_and_post(self):
        nodes = {
            "it": _node("it", "dataset_iterator"),
            "proc": _node("proc", "transform"),
            "col": _node("col", "collect_results"),
            "report": _node("report", "summary"),
        }
        edges = [
            _edge("e1", "it", "v", "proc", "x"),
            _edge("e2", "proc", "out", "col", "item"),
            _edge("e3", "col", "collection", "report", "in"),
        ]
        it, pre, loop, collect, post = detect_iterator_structure(nodes, edges)
        assert it == "it"
        assert set(loop) == {"it", "proc", "col"}
        assert collect == ["col"]
        assert post == ["report"]
        assert pre == []

    def test_namespaced_iterator_is_detected(self):
        nodes = {"it": _node("it", "synapchart_builtin.dataset_iterator")}
        edges = []
        it, *_ = detect_iterator_structure(nodes, edges)
        assert it == "it"


# ---------------------------------------------------------------------------
# _compute_source_hash
# ---------------------------------------------------------------------------

class TestComputeSourceHash:
    def test_builtin_block_hash_is_stable(self, make_block):
        blk = make_block("plain", lambda i, p: {})
        assert _compute_source_hash(blk) == _compute_source_hash(blk)

    def test_custom_source_change_changes_hash(self, make_block):
        blk = make_block("custom", lambda i, p: {})
        blk._source_code = "version one"
        h1 = _compute_source_hash(blk)
        blk._source_code = "version two"
        h2 = _compute_source_hash(blk)
        assert h1 != h2


# ---------------------------------------------------------------------------
# End-to-end run
# ---------------------------------------------------------------------------

class TestRun:
    async def test_linear_pipeline_runs_and_stores_outputs(self, make_block):
        make_block(
            "source",
            lambda i, p: {"out": NeuroData(data_type="lfp", array=np.arange(5.0))},
            outputs=[PortDefinition("out", "NeuroData[lfp]", "")],
        )
        make_block(
            "scale",
            lambda i, p: {
                "out": NeuroData(data_type="lfp", array=i["x"].array * 2.0)
            },
            inputs=[PortDefinition("x", "NeuroData[lfp]", "")],
            outputs=[PortDefinition("out", "NeuroData[lfp]", "")],
        )
        wf = {
            "nodes": [_node("n1", "source"), _node("n2", "scale")],
            "edges": [_edge("e1", "n1", "out", "n2", "x")],
        }
        ex = PipelineExecutor(wf)
        messages = await _drain(ex.run(use_cache=False))

        statuses = _statuses(messages)
        assert "plan" in statuses
        assert statuses.count("done") == 2
        assert messages[-1]["message"] == "Pipeline complete."
        np.testing.assert_array_equal(ex.outputs["n2"]["out"].array, np.arange(5.0) * 2.0)

    async def test_second_run_uses_cache(self, make_block):
        calls = {"source": 0, "scale": 0}

        def src_run(i, p):
            calls["source"] += 1
            return {"out": NeuroData(data_type="lfp", array=np.ones(3))}

        def scale_run(i, p):
            calls["scale"] += 1
            return {"out": NeuroData(data_type="lfp", array=i["x"].array + 1)}

        make_block("source", src_run, outputs=[PortDefinition("out", "NeuroData[lfp]", "")])
        make_block(
            "scale", scale_run,
            inputs=[PortDefinition("x", "NeuroData[lfp]", "")],
            outputs=[PortDefinition("out", "NeuroData[lfp]", "")],
        )
        wf = {
            "nodes": [_node("n1", "source"), _node("n2", "scale")],
            "edges": [_edge("e1", "n1", "out", "n2", "x")],
        }

        await _drain(PipelineExecutor(wf).run(use_cache=False))
        assert calls == {"source": 1, "scale": 1}

        messages = await _drain(PipelineExecutor(wf).run(use_cache=True))
        # No block re-executed; both served from cache.
        assert calls == {"source": 1, "scale": 1}
        assert _statuses(messages).count("cached") == 2

    async def test_parameter_change_invalidates_cache(self, make_block):
        calls = {"n": 0}

        def run(i, p):
            calls["n"] += 1
            return {"out": NeuroData(data_type="lfp", array=np.array([p.get("gain", 1.0)]))}

        make_block(
            "gainblock", run,
            outputs=[PortDefinition("out", "NeuroData[lfp]", "")],
        )
        wf1 = {"nodes": [_node("n1", "gainblock", gain=1.0)], "edges": []}
        wf2 = {"nodes": [_node("n1", "gainblock", gain=2.0)], "edges": []}

        await _drain(PipelineExecutor(wf1).run(use_cache=False))
        # Changed parameter must miss the cache even with use_cache=True.
        messages = await _drain(PipelineExecutor(wf2).run(use_cache=True))
        assert calls["n"] == 2
        assert "cached" not in _statuses(messages)

    async def test_block_exception_is_reported_as_error(self, make_block):
        def boom(i, p):
            raise RuntimeError("kaboom")

        make_block("bad", boom, outputs=[PortDefinition("out", "NeuroData[any]", "")])
        wf = {"nodes": [_node("n1", "bad")], "edges": []}
        messages = await _drain(PipelineExecutor(wf).run(use_cache=False))

        errors = [m for m in messages if m.get("status") == "error"]
        assert len(errors) == 1
        assert "kaboom" in errors[0]["message"]
        assert errors[0]["node_id"] == "n1"

    async def test_validation_error_short_circuits_run(self):
        # Node references an unregistered block — run must stop at validation.
        wf = {"nodes": [_node("n1", "missing_block")], "edges": []}
        messages = await _drain(PipelineExecutor(wf).run(use_cache=False))
        assert any(m.get("level") == "error" for m in messages)
        assert all(m.get("message") != "Pipeline complete." for m in messages)

    async def test_disp_output_is_streamed(self, make_block):
        def run(i, p):
            disp("hello from block")  # noqa: F821 — injected builtin
            return {"out": NeuroData(data_type="any", array=np.zeros(1))}

        make_block("talker", run, outputs=[PortDefinition("out", "NeuroData[any]", "")])
        wf = {"nodes": [_node("n1", "talker")], "edges": []}
        messages = await _drain(PipelineExecutor(wf).run(use_cache=False))
        disp_msgs = [m for m in messages if m.get("status") == "disp"]
        assert any("hello from block" in m["message"] for m in disp_msgs)
