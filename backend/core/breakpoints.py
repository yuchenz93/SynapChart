"""Session-level breakpoint registry for the SynapChart workspace debugger.

Breakpoints are node-level; they are session-only and never persisted to disk.
"""

from __future__ import annotations

_breakpoints: set[str] = set()   # set of node_ids


def set_breakpoint(node_id: str) -> None:
    _breakpoints.add(node_id)


def clear_breakpoint(node_id: str) -> None:
    _breakpoints.discard(node_id)


def has_breakpoint(node_id: str) -> bool:
    return node_id in _breakpoints


def all_breakpoints() -> list[str]:
    return list(_breakpoints)


def clear_all() -> None:
    _breakpoints.clear()
