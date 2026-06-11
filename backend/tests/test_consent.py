"""Tests for the load-time code-consent gate (api.files).

Opening a workflow that contains custom code must not execute that code until
the user has consented.  These tests pin both halves of that guarantee:
``_detect_executable_code`` surfaces every code source, and ``_process_workflow``
only registers embedded Python when ``trusted=True``.
"""

from __future__ import annotations

import pytest

from api.files import _detect_executable_code, _process_workflow
from core.block_registry import get_block


EMBEDDED_SOURCE = """
from blocks.base import BlockBase, PortDefinition
from neurodata.types import NeuroData
import numpy as np

class MyBlock(BlockBase):
    block_type_id = "myblock"
    display_name = "My Block"
    category = "Test"
    description = ""
    inputs = []
    outputs = [PortDefinition("out", "NeuroData[any]", "")]

    def run(self, inputs, parameters):
        return {"out": NeuroData(data_type="any", array=np.zeros(1))}
"""


def _packed_workflow():
    return {
        "schema_version": "2.0",
        "packed": True,
        "libraries": [{"id": "mylib", "version": "0.1.0", "priority": 2}],
        "nodes": [],
        "edges": [],
        "embedded_blocks": {
            "mylib.myblock": {
                "type": "python",
                "library_id": "mylib",
                "library_version": "0.1.0",
                "source_code": EMBEDDED_SOURCE,
            }
        },
    }


class TestDetectExecutableCode:
    def test_clean_workflow_has_no_code(self):
        wf = {"nodes": [{"node_id": "n", "block_type_id": "builtin.x"}], "edges": []}
        assert _detect_executable_code(wf) == []

    def test_local_blocks_are_listed(self):
        wf = {
            "local_blocks": [
                {"block_type_id": "my_local", "source_snippet": "x = 1\nreturn {}"}
            ],
        }
        manifest = _detect_executable_code(wf)
        assert len(manifest) == 1
        assert manifest[0]["block_type_id"] == "my_local"
        assert manifest[0]["kind"] == "local_block"
        assert manifest[0]["line_count"] == 2

    def test_embedded_python_blocks_are_listed(self):
        manifest = _detect_executable_code(_packed_workflow())
        assert len(manifest) == 1
        assert manifest[0]["kind"] == "embedded_python"
        assert manifest[0]["block_type_id"] == "mylib.myblock"
        assert manifest[0]["library_id"] == "mylib"
        assert "class MyBlock" in manifest[0]["source"]

    def test_nested_embedded_blocks_are_listed(self):
        wf = {
            "embedded_blocks": {
                "lib.outer": {
                    "type": "composite",
                    "library_id": "lib",
                    "embedded_blocks": {
                        "lib.inner": {
                            "type": "python",
                            "library_id": "lib",
                            "source_code": "x = 1",
                        }
                    },
                }
            }
        }
        manifest = _detect_executable_code(wf)
        ids = {m["block_type_id"] for m in manifest}
        assert "lib.inner" in ids


class TestTrustedGating:
    def test_untrusted_load_does_not_register_embedded_code(self):
        _process_workflow(_packed_workflow(), trusted=False)
        # The embedded block must NOT have been exec'd / registered.
        with pytest.raises(KeyError):
            get_block("mylib.myblock")

    def test_trusted_load_registers_embedded_code(self):
        _process_workflow(_packed_workflow(), trusted=True)
        block = get_block("mylib.myblock")
        assert block.block_type_id == "myblock"

    def test_untrusted_load_still_returns_usable_workflow(self):
        # Gating must not break rendering — the workflow still comes back.
        wf, redirects, migrated, warnings = _process_workflow(
            _packed_workflow(), trusted=False
        )
        assert wf["packed"] is True
        assert isinstance(warnings, list)
