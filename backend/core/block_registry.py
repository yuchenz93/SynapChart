"""Backward-compatibility shim for the old flat block registry.

All calls are delegated to ``core.library_registry`` which implements the
full namespaced library system described in Doc 10.

Existing code that imports from this module (executor, validator, api/blocks)
continues to work without modification.
"""


from __future__ import annotations

from core.library_registry import (
    discover_all_libraries as _discover_all,
    get_block,           # noqa: F401 — re-exported
    all_blocks,          # noqa: F401
    register_block,      # noqa: F401
    unregister_block,    # noqa: F401
    LEGACY_COMPOSITE_DIR as COMPOSITE_DIR,  # noqa: F401 — used by api/blocks.py
)


def discover_blocks() -> None:
    """Legacy entry point — now delegates to discover_all_libraries()."""
    _discover_all()


def discover_composite_blocks() -> None:
    """No-op: composite block loading is handled inside discover_all_libraries()."""
    pass
