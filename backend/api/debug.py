"""Debugger API endpoints for the SynapChart workspace debugger."""

from __future__ import annotations

from fastapi import APIRouter

from core.breakpoints import set_breakpoint, clear_breakpoint, all_breakpoints, clear_all
from core.executor import signal_continue, _session_cache_keys
from core.workspace import summarize_outputs, get_variable_detail, get_variable_preview

router = APIRouter()


# ---------------------------------------------------------------------------
# Breakpoint management
# ---------------------------------------------------------------------------

@router.post("/breakpoint/set")
async def set_bp(node_id: str):
    set_breakpoint(node_id)
    return {"node_id": node_id, "breakpoint": True}


@router.post("/breakpoint/clear")
async def clear_bp(node_id: str):
    clear_breakpoint(node_id)
    return {"node_id": node_id, "breakpoint": False}


@router.post("/breakpoint/clear-all")
async def clear_all_bp():
    clear_all()
    return {"cleared": True}


@router.get("/breakpoints")
async def list_bp():
    return {"breakpoints": all_breakpoints()}


# ---------------------------------------------------------------------------
# Continue (resume a paused pipeline)
# ---------------------------------------------------------------------------

@router.post("/continue")
async def continue_execution():
    """Resume a pipeline paused at a breakpoint."""
    signal_continue()
    return {"status": "resumed"}


# ---------------------------------------------------------------------------
# Workspace data
# ---------------------------------------------------------------------------

@router.get("/workspace/{node_id}")
async def get_workspace_node(node_id: str):
    """Return the variable summary table for one completed node."""
    cache_key = _session_cache_keys.get(node_id)
    if cache_key is None:
        return {"error": "No cached output for this node in current session."}
    return {"node_id": node_id, "variables": summarize_outputs(node_id, cache_key)}


@router.get("/workspace/{node_id}/{port_id}/detail")
async def get_variable_detail_ep(node_id: str, port_id: str):
    """Return full detail (summary + statistics + first 500 rows) for one port output."""
    cache_key = _session_cache_keys.get(node_id)
    if cache_key is None:
        return {"error": "No cache key found for this node."}
    return get_variable_detail(cache_key, port_id)


@router.get("/workspace/{node_id}/{port_id}/preview")
async def get_variable_preview_ep(node_id: str, port_id: str):
    """Return a base64 PNG preview plot for one port output."""
    cache_key = _session_cache_keys.get(node_id)
    if cache_key is None:
        return {"error": "No cache key found for this node."}
    return get_variable_preview(cache_key, port_id)
