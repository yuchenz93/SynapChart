"""Tests for the v1 -> v2 workflow schema migration (api.files._migrate_v1_to_v2).

Migration namespaces legacy flat block IDs (``bandpass_filter``) to library-
qualified IDs (``synapchart_builtin.bandpass_filter``), resolving forwarding
aliases and rebuilding the ``libraries`` array.  These paths are exercised by
every load of an older workflow, so they directly affect reproducibility of
shared files.
"""

from __future__ import annotations

import pytest

from api.files import _migrate_v1_to_v2


@pytest.fixture
def seeded_registry(clean_registry):
    """Populate the flat index and forwarding aliases with known fixtures."""
    reg = clean_registry
    reg._flat_index.clear()
    reg._forwarding_aliases.clear()
    reg._flat_index["bandpass_filter"] = ["synapchart_builtin.bandpass_filter"]
    reg._flat_index["fancy_decode"] = ["coollib.fancy_decode"]
    reg._forwarding_aliases["old_filter"] = "synapchart_builtin.bandpass_filter"
    return reg


def _node(node_id, bid):
    return {"node_id": node_id, "block_type_id": bid, "parameters": {}}


class TestSchemaMigration:
    def test_flat_builtin_id_is_namespaced(self, seeded_registry):
        wf = {"schema_version": "1.0", "nodes": [_node("n1", "bandpass_filter")], "edges": []}
        migrated, redirects = _migrate_v1_to_v2(wf)
        assert migrated["schema_version"] == "2.0"
        assert migrated["nodes"][0]["block_type_id"] == "synapchart_builtin.bandpass_filter"
        assert redirects == []

    def test_builtin_library_always_present(self, seeded_registry):
        wf = {"schema_version": "1.0", "nodes": [_node("n1", "bandpass_filter")], "edges": []}
        migrated, _ = _migrate_v1_to_v2(wf)
        lib_ids = [lib["id"] for lib in migrated["libraries"]]
        assert "synapchart_builtin" in lib_ids

    def test_third_party_library_added_with_priority(self, seeded_registry):
        wf = {"schema_version": "1.0", "nodes": [_node("n1", "fancy_decode")], "edges": []}
        migrated, _ = _migrate_v1_to_v2(wf)
        assert migrated["nodes"][0]["block_type_id"] == "coollib.fancy_decode"
        lib_ids = [lib["id"] for lib in migrated["libraries"]]
        assert "coollib" in lib_ids

    def test_forwarding_alias_records_redirect(self, seeded_registry):
        wf = {"schema_version": "1.0", "nodes": [_node("n1", "old_filter")], "edges": []}
        migrated, redirects = _migrate_v1_to_v2(wf)
        assert migrated["nodes"][0]["block_type_id"] == "synapchart_builtin.bandpass_filter"
        assert redirects == [
            {"old_id": "old_filter", "new_id": "synapchart_builtin.bandpass_filter"}
        ]

    def test_local_block_id_is_left_untouched(self, seeded_registry):
        wf = {
            "schema_version": "1.0",
            "local_blocks": [{"block_type_id": "my_local"}],
            "nodes": [_node("n1", "my_local")],
            "edges": [],
        }
        migrated, redirects = _migrate_v1_to_v2(wf)
        assert migrated["nodes"][0]["block_type_id"] == "my_local"
        # A local block must never be mistaken for a library.
        lib_ids = [lib["id"] for lib in migrated["libraries"]]
        assert "my_local" not in lib_ids

    def test_unknown_flat_id_passes_through(self, seeded_registry):
        wf = {"schema_version": "1.0", "nodes": [_node("n1", "mystery_block")], "edges": []}
        migrated, redirects = _migrate_v1_to_v2(wf)
        assert migrated["nodes"][0]["block_type_id"] == "mystery_block"
        assert redirects == []

    def test_already_namespaced_id_is_preserved(self, seeded_registry):
        wf = {
            "schema_version": "1.0",
            "nodes": [_node("n1", "coollib.fancy_decode")],
            "edges": [],
        }
        migrated, _ = _migrate_v1_to_v2(wf)
        assert migrated["nodes"][0]["block_type_id"] == "coollib.fancy_decode"
        lib_ids = [lib["id"] for lib in migrated["libraries"]]
        assert "coollib" in lib_ids

    def test_original_workflow_not_mutated(self, seeded_registry):
        wf = {"schema_version": "1.0", "nodes": [_node("n1", "bandpass_filter")], "edges": []}
        _migrate_v1_to_v2(wf)
        # Source dict's node should still hold the original flat id.
        assert wf["nodes"][0]["block_type_id"] == "bandpass_filter"
        assert wf["schema_version"] == "1.0"
