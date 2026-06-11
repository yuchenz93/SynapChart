"""Tests for batch execution driven by dataset_iterator (core.executor)."""

from __future__ import annotations

import numpy as np
import pytest

from blocks.base import ParameterDefinition, PortDefinition
from core.executor import PipelineExecutor, _read_csv_rows, _row_to_outputs
from neurodata.types import NeuroData


async def _drain(agen):
    return [msg async for msg in agen]


def _statuses(messages):
    return [m.get("status") for m in messages if m.get("status")]


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

class TestReadCsvRows:
    def test_reads_rows_with_header(self, tmp_path):
        csv = tmp_path / "s.csv"
        csv.write_text("sid,value\ns1,10\ns2,20\n", encoding="utf-8")
        rows = _read_csv_rows(str(csv), {"skip_header": True})
        assert rows == [{"sid": "s1", "value": "10"}, {"sid": "s2", "value": "20"}]

    def test_skips_blank_rows(self, tmp_path):
        csv = tmp_path / "s.csv"
        csv.write_text("sid,value\ns1,10\n\n   \ns2,20\n", encoding="utf-8")
        rows = _read_csv_rows(str(csv), {"skip_header": True})
        assert len(rows) == 2

    def test_no_header_uses_numeric_keys(self, tmp_path):
        csv = tmp_path / "s.csv"
        csv.write_text("a,1\nb,2\n", encoding="utf-8")
        rows = _read_csv_rows(str(csv), {"skip_header": False})
        assert rows[0] == {"0": "a", "1": "1"}

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            _read_csv_rows("does/not/exist.csv", {})


class TestRowToOutputs:
    def test_maps_ports_to_columns(self):
        row = {"sid": "s1", "lfp": "/path/a.npy", "spk": "/path/b.npy"}
        mappings = {"lfp_file": "lfp", "spike_file": "spk"}
        assert _row_to_outputs(row, mappings) == {
            "lfp_file": "/path/a.npy",
            "spike_file": "/path/b.npy",
        }

    def test_missing_column_yields_empty_string(self):
        assert _row_to_outputs({"a": "1"}, {"port": "missing"}) == {"port": ""}


# ---------------------------------------------------------------------------
# Full batch run
# ---------------------------------------------------------------------------

class TestBatchRun:
    async def test_batch_iterates_and_collects(self, make_block, clean_registry, tmp_path):
        csv = tmp_path / "sessions.csv"
        csv.write_text("sid,value\ns1,1\ns2,2\ns3,3\n", encoding="utf-8")

        # Iterator stand-in: detected by block_type_id; outputs are injected
        # from CSV rows by the executor, so run() is never called.
        it = make_block("dataset_iterator", lambda i, p: {}, outputs=[])
        it.is_iterator = True

        # Per-iteration processor: turns the CSV string into a 1-element array.
        make_block(
            "to_array",
            lambda i, p: {
                "out": NeuroData(data_type="any", array=np.array([float(i["x"])]))
            },
            inputs=[PortDefinition("x", "str", "")],
            outputs=[PortDefinition("out", "NeuroData[any]", "")],
        )

        # collect_results stand-in for validation; the executor calls the real
        # CollectResults.finalize() to stack accumulated items.
        make_block(
            "collect_results",
            lambda i, p: {"collection": i.get("item")},
            inputs=[PortDefinition("item", "NeuroData[any]", "")],
            outputs=[PortDefinition("collection", "NeuroData[any]", "")],
            parameters=[
                ParameterDefinition("axis", "int", 0, ""),
                ParameterDefinition("keep_metadata_from", "enum:first,last", "first", ""),
            ],
        )

        wf = {
            "nodes": [
                {
                    "node_id": "it",
                    "block_type_id": "dataset_iterator",
                    "parameters": {
                        "csv_path": str(csv),
                        "column_mappings": '{"value": "value"}',
                        "skip_header": True,
                        "session_id_col": "sid",
                    },
                },
                {"node_id": "proc", "block_type_id": "to_array", "parameters": {}},
                {"node_id": "col", "block_type_id": "collect_results", "parameters": {}},
            ],
            "edges": [
                {"edge_id": "e1", "source_node_id": "it", "source_port_id": "value",
                 "target_node_id": "proc", "target_port_id": "x"},
                {"edge_id": "e2", "source_node_id": "proc", "source_port_id": "out",
                 "target_node_id": "col", "target_port_id": "item"},
            ],
        }

        ex = PipelineExecutor(wf)
        messages = await _drain(ex.run(use_cache=False))
        statuses = _statuses(messages)

        assert "batch_start" in statuses
        assert statuses.count("batch_progress") == 3
        assert "batch_done" in statuses

        collection = ex.outputs["col"]["collection"]
        assert isinstance(collection, NeuroData)
        # Three iterations stacked along axis 0 -> shape (3, 1).
        assert collection.array.shape == (3, 1)
        np.testing.assert_array_equal(
            collection.array.reshape(-1), np.array([1.0, 2.0, 3.0])
        )

    async def test_batch_reports_total_session_count(self, make_block, tmp_path):
        csv = tmp_path / "sessions.csv"
        csv.write_text("sid,value\ns1,1\ns2,2\n", encoding="utf-8")
        it = make_block("dataset_iterator", lambda i, p: {}, outputs=[])
        it.is_iterator = True
        make_block(
            "to_array",
            lambda i, p: {"out": NeuroData(data_type="any", array=np.array([float(i["x"])]))},
            inputs=[PortDefinition("x", "str", "")],
            outputs=[PortDefinition("out", "NeuroData[any]", "")],
        )
        wf = {
            "nodes": [
                {"node_id": "it", "block_type_id": "dataset_iterator",
                 "parameters": {"csv_path": str(csv),
                                "column_mappings": '{"value": "value"}',
                                "skip_header": True, "session_id_col": "sid"}},
                {"node_id": "proc", "block_type_id": "to_array", "parameters": {}},
            ],
            "edges": [
                {"edge_id": "e1", "source_node_id": "it", "source_port_id": "value",
                 "target_node_id": "proc", "target_port_id": "x"},
            ],
        }
        messages = await _drain(PipelineExecutor(wf).run(use_cache=False))
        start = next(m for m in messages if m.get("status") == "batch_start")
        assert start["total"] == 2
