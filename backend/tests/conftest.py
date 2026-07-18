"""Shared pytest fixtures and import setup for the SynapChart backend tests.

The backend uses *flat* absolute imports (``from core.x import y``) that assume
``backend/`` is on ``sys.path``.  In dev and under ``pip install -e .`` this is
arranged by ``backend/__init__.py``, but pytest imports test modules as
top-level modules and does not necessarily import the ``backend`` package first.
Inserting the backend directory here makes ``from core. / from blocks.`` imports
resolve identically whether tests are run from the repo root (as CI does) or
from inside ``backend/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import numpy as np
import pytest

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


# ---------------------------------------------------------------------------
# Cache isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Point the on-disk checkpoint cache at a per-test temp directory.

    ``core.checkpoint`` reads the module-level ``CACHE_DIR`` inside each
    function body, so patching the attribute redirects has_cache/save_cache/
    load_cache/clear_cache for the duration of the test without touching the
    developer's real ``.synapchart_cache`` directory.
    """
    import core.checkpoint as checkpoint

    cache_dir = tmp_path / "_cache"
    monkeypatch.setattr(checkpoint, "CACHE_DIR", cache_dir)
    yield cache_dir


# ---------------------------------------------------------------------------
# Registry isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_registry():
    """Snapshot and restore the global library-registry dicts around each test.

    The registry is process-global mutable state.  Snapshotting it keeps tests
    that register blocks from leaking into one another, and lets migration tests
    populate ``_flat_index`` / ``_forwarding_aliases`` in isolation.
    """
    import core.library_registry as reg

    snapshots = {
        name: dict(getattr(reg, name))
        for name in ("_libraries", "_block_registry", "_forwarding_aliases", "_flat_index")
    }
    try:
        yield reg
    finally:
        for name, original in snapshots.items():
            target = getattr(reg, name)
            target.clear()
            target.update(original)


# ---------------------------------------------------------------------------
# Block factory
# ---------------------------------------------------------------------------

@pytest.fixture
def make_block(clean_registry):
    """Factory that builds and registers a minimal BlockBase subclass.

    Returns a callable ``make_block(block_type_id, run, *, inputs, outputs,
    parameters, register=True)`` that returns the registered instance.  ``run``
    receives ``(inputs, parameters)`` and returns the output port dict.
    """
    def _make(
        block_type_id,
        run,
        *,
        inputs=None,
        outputs=None,
        parameters=None,
        category="Test",
        register=True,
        library_id=None,
    ):
        cls = type(
            f"_TB_{block_type_id}",
            (BlockBase,),
            {
                "block_type_id": block_type_id,
                "display_name": block_type_id,
                "category": category,
                "description": "Test block.",
                "inputs": inputs or [],
                "outputs": outputs or [],
                "parameters": parameters or [],
                "run": lambda self, inputs, parameters: run(inputs, parameters),
            },
        )
        instance = cls()
        if register:
            clean_registry.register_block(instance, library_id)
        return instance

    return _make


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_lfp():
    """A small 2-D LFP NeuroData (1000 samples x 2 channels)."""
    t = np.linspace(0, 1, 1000)
    arr = np.column_stack([np.sin(2 * np.pi * 8 * t), np.cos(2 * np.pi * 8 * t)])
    return NeuroData(
        data_type="lfp",
        array=arr,
        sampling_rate=1000.0,
        timestamps=t,
        channel_names=["ch0", "ch1"],
    )


# Re-export so tests can build ports without re-importing.
__all__ = ["BlockBase", "ParameterDefinition", "PortDefinition", "NeuroData"]
