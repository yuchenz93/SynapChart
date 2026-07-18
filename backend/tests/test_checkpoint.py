"""Tests for the per-node result cache (core.checkpoint).

These cover the reproducibility-critical guarantee: a node's cache key changes
if and only if its identity, parameters, upstream keys, or implementation source
change — so edits invalidate exactly the affected node and its descendants.
"""

from __future__ import annotations

import numpy as np

from core.checkpoint import (
    _make_key,
    clear_cache,
    has_cache,
    load_cache,
    save_cache,
)
from neurodata.types import NeuroData


class TestMakeKey:
    def test_deterministic_for_identical_inputs(self):
        k1 = _make_key("n1", "blk", {"a": 1}, ["up1"], "src")
        k2 = _make_key("n1", "blk", {"a": 1}, ["up1"], "src")
        assert k1 == k2

    def test_key_is_16_hex_chars(self):
        k = _make_key("n1", "blk", {}, [], "")
        assert len(k) == 16
        int(k, 16)  # parses as hex

    def test_node_id_does_not_affect_key(self):
        # node_id is only for human context; identical work => identical key.
        k1 = _make_key("node_A", "blk", {"a": 1}, [], "src")
        k2 = _make_key("node_B", "blk", {"a": 1}, [], "src")
        assert k1 == k2

    def test_parameter_change_changes_key(self):
        base = _make_key("n", "blk", {"low": 4.0}, [], "src")
        changed = _make_key("n", "blk", {"low": 8.0}, [], "src")
        assert base != changed

    def test_block_type_change_changes_key(self):
        a = _make_key("n", "blk_a", {}, [], "src")
        b = _make_key("n", "blk_b", {}, [], "src")
        assert a != b

    def test_source_hash_change_changes_key(self):
        old = _make_key("n", "blk", {}, [], "src_v1")
        new = _make_key("n", "blk", {}, [], "src_v2")
        assert old != new

    def test_upstream_key_change_changes_key(self):
        a = _make_key("n", "blk", {}, ["up_v1"], "src")
        b = _make_key("n", "blk", {}, ["up_v2"], "src")
        assert a != b

    def test_input_key_order_is_normalized(self):
        # Predecessor order must not matter: keys are sorted before hashing.
        a = _make_key("n", "blk", {}, ["x", "y"], "src")
        b = _make_key("n", "blk", {}, ["y", "x"], "src")
        assert a == b


class TestSaveLoadRoundtrip:
    def test_has_cache_false_before_save(self):
        key = _make_key("n", "blk", {}, [], "")
        assert has_cache(key) is False

    def test_save_then_load_returns_equivalent_outputs(self):
        key = _make_key("n", "blk", {"p": 1}, [], "")
        outputs = {
            "out": NeuroData(data_type="lfp", array=np.arange(10.0), sampling_rate=1000.0)
        }
        save_cache(key, outputs)
        assert has_cache(key) is True

        loaded = load_cache(key)
        assert set(loaded) == {"out"}
        nd = loaded["out"]
        assert nd.data_type == "lfp"
        assert nd.sampling_rate == 1000.0
        np.testing.assert_array_equal(nd.array, np.arange(10.0))

    def test_save_preserves_primitive_outputs(self):
        key = _make_key("scalar", "blk", {}, [], "")
        save_cache(key, {"value": 3.14, "label": "abc"})
        loaded = load_cache(key)
        assert loaded == {"value": 3.14, "label": "abc"}


class TestClearCache:
    def test_clear_all_removes_every_file(self):
        # Vary a parameter so each node gets a distinct key (node_id alone does not).
        for i in range(3):
            save_cache(_make_key("n", "blk", {"i": i}, [], ""), {"v": i})
        deleted = clear_cache()
        assert deleted == 3
        assert clear_cache() == 0  # nothing left

    def test_clear_single_key_only_removes_that_file(self):
        k_keep = _make_key("n", "blk", {"which": "keep"}, [], "")
        k_drop = _make_key("n", "blk", {"which": "drop"}, [], "")
        save_cache(k_keep, {"v": 1})
        save_cache(k_drop, {"v": 2})

        deleted = clear_cache(k_drop)
        assert deleted == 1
        assert has_cache(k_drop) is False
        assert has_cache(k_keep) is True

    def test_clear_missing_key_returns_zero(self):
        assert clear_cache("does_not_exist") == 0

    def test_clear_on_absent_dir_returns_zero(self):
        # isolated_cache points CACHE_DIR at a not-yet-created temp dir.
        assert clear_cache() == 0
