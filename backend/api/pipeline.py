"""Pipeline execution endpoints and WebSocket log streaming."""


from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.executor import PipelineExecutor, signal_continue
from core.checkpoint import clear_cache as _clear_cache_files

router = APIRouter()

# ---------------------------------------------------------------------------
# Global execution state (v1: single pipeline at a time)
# ---------------------------------------------------------------------------

_run_status: str = "idle"          # idle | running | done | error | stopped
_active_executor: PipelineExecutor | None = None
_node_statuses: dict[str, str] = {}

# Fan-out: one asyncio.Queue per connected WebSocket client.
# The background run task puts messages into every queue.
_ws_queues: set[asyncio.Queue] = set()


async def _broadcast(msg: dict) -> None:
    """Put a log message into every connected client's queue."""
    for q in _ws_queues:
        await q.put(msg)


def _update_node_status(msg: dict) -> None:
    """Update the in-memory node status map from a log message."""
    if msg.get("node_id") and msg.get("status"):
        _node_statuses[msg["node_id"]] = msg["status"]


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class RunOptions(BaseModel):
    use_cache: bool = True
    target_node_id: str | None = None


class RunRequest(BaseModel):
    workflow: dict
    run_options: RunOptions = RunOptions()


class StepRequest(BaseModel):
    workflow: dict
    node_id: str


class ClearCacheRequest(BaseModel):
    node_id: str | None = None   # None = clear everything


class RunResponse(BaseModel):
    run_id: str
    status: str


# ---------------------------------------------------------------------------
# Background execution task
# ---------------------------------------------------------------------------

async def _run_background(
    executor: PipelineExecutor,
    use_cache: bool,
) -> None:
    """Drive executor.run() and broadcast every log message to WS clients.
    Updates module-level state machine throughout.
    """
    global _run_status, _active_executor, _node_statuses

    _run_status = "running"
    _node_statuses = {}

    try:
        async for msg in executor.run(use_cache=use_cache):
            _update_node_status(msg)
            await _broadcast(msg)

            # Detect user stop or error from within the generator
            if msg.get("status") == "stopped":
                _run_status = "stopped"
                _active_executor = None
                return
            if msg.get("level") == "error":
                _run_status = "error"

        if _run_status == "running":
            _run_status = "done"
        await _broadcast({"level": "info", "node_id": None,
                          "message": _run_status, "status": _run_status})
    except Exception as exc:  # noqa: BLE001
        _run_status = "error"
        await _broadcast({"level": "error", "node_id": None, "message": str(exc), "status": "error"})
    finally:
        _active_executor = None


async def _step_background(executor: PipelineExecutor, node_id: str) -> None:
    """Drive executor.step() and broadcast log messages."""
    global _run_status, _active_executor

    _run_status = "running"
    try:
        async for msg in executor.step(node_id):
            _update_node_status(msg)
            await _broadcast(msg)
            if msg.get("level") == "error":
                _run_status = "error"
        if _run_status == "running":
            _run_status = "done"
        await _broadcast({"level": "info", "node_id": None,
                          "message": _run_status, "status": _run_status})
    except Exception as exc:  # noqa: BLE001
        _run_status = "error"
        await _broadcast({"level": "error", "node_id": None, "message": str(exc), "status": "error"})
    finally:
        _active_executor = None


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@router.post("/run", response_model=RunResponse)
async def run_pipeline(request: RunRequest) -> RunResponse:
    """Run entire pipeline from scratch (ignores checkpoints)."""
    global _active_executor, _run_status
    if _run_status == "running":
        raise HTTPException(status_code=409, detail={
            "error": "already_running",
            "message": "A pipeline is already running. Stop it first.",
            "details": {},
        })
    run_id = str(uuid.uuid4())
    _active_executor = PipelineExecutor(request.workflow)
    asyncio.create_task(_run_background(_active_executor, use_cache=False))
    return RunResponse(run_id=run_id, status="started")


@router.post("/run-from-cache", response_model=RunResponse)
async def run_from_cache(request: RunRequest) -> RunResponse:
    """Run pipeline, loading cached results where available."""
    global _active_executor, _run_status
    if _run_status == "running":
        raise HTTPException(status_code=409, detail={
            "error": "already_running",
            "message": "A pipeline is already running. Stop it first.",
            "details": {},
        })
    run_id = str(uuid.uuid4())
    _active_executor = PipelineExecutor(request.workflow)
    asyncio.create_task(_run_background(_active_executor, use_cache=True))
    return RunResponse(run_id=run_id, status="started")


@router.post("/step", response_model=RunResponse)
async def step_pipeline(request: StepRequest) -> RunResponse:
    """Execute a single named node (upstream inputs must be cached)."""
    global _active_executor, _run_status
    if _run_status == "running":
        raise HTTPException(status_code=409, detail={
            "error": "already_running",
            "message": "A pipeline is already running. Stop it first.",
            "details": {},
        })
    run_id = str(uuid.uuid4())
    _active_executor = PipelineExecutor(request.workflow)
    asyncio.create_task(_step_background(_active_executor, request.node_id))
    return RunResponse(run_id=run_id, status="started")


@router.post("/stop")
async def stop_pipeline() -> dict:
    """Interrupt a running pipeline after the current node finishes."""
    global _run_status
    if _active_executor is not None:
        _active_executor.stop()
    # Unblock a paused pipeline so it can check the stop flag and exit.
    signal_continue()
    _run_status = "stopped"
    return {"status": "stopped"}


@router.get("/status")
async def get_status() -> dict:
    """Return current execution state and per-node statuses."""
    return {
        "run_status": _run_status,
        "node_statuses": dict(_node_statuses),
    }


@router.post("/clear-cache")
async def clear_cache_endpoint(request: ClearCacheRequest) -> dict:
    """Clear cached results for one node or the entire pipeline.

    When node_id is provided, the cache key for that node is looked up from
    the most recent executor state. If unavailable, all cache files are cleared.
    """
    deleted = _clear_cache_files()
    return {"status": "cleared", "files_deleted": deleted}


# ---------------------------------------------------------------------------
# WebSocket log streaming
# ---------------------------------------------------------------------------

@router.websocket("/logs")
async def logs_websocket(websocket: WebSocket) -> None:
    """Stream live execution log messages to the client as JSON.

    Each message follows the schema::

        {"level": "info"|"warning"|"error",
         "node_id": str | null,
         "message": str,
         "status": "running"|"done"|"cached"|"error"|"stopped" | null}

    The client connects before calling /run and stays connected for the
    duration of the pipeline. Multiple simultaneous clients are supported.
    """
    await websocket.accept()
    q: asyncio.Queue = asyncio.Queue()
    _ws_queues.add(q)
    try:
        while True:
            msg = await q.get()
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    finally:
        _ws_queues.discard(q)
