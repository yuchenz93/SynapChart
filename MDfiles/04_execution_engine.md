# SynapChart — Doc 04: Execution Engine + Checkpoints

## Overview

The execution engine takes a workflow JSON, resolves the execution order, runs blocks in sequence, and manages a per-node result cache (checkpoints). It supports three execution modes:

1. **Full run** — execute all nodes from scratch, ignoring any cached results
2. **Cached run** — execute nodes in order, loading cached results for nodes that have not changed since the last run
3. **Step** — execute a single named node (its upstream inputs must already be cached)

The engine streams log messages to connected WebSocket clients as nodes execute.

---

## DAG Resolution — `core/graph.py`

Before execution, the workflow graph is resolved into an ordered execution list using topological sort (Kahn's algorithm).

```python
# core/graph.py
from collections import defaultdict, deque

def topological_sort(nodes: list[dict], edges: list[dict]) -> list[str]:
    """
    Returns a list of node_ids in valid execution order.
    Raises ValueError if the graph contains a cycle.

    Args:
        nodes: list of workflow node dicts (must have 'node_id')
        edges: list of workflow edge dicts (must have 'source_node_id', 'target_node_id')
    """
    in_degree = {n["node_id"]: 0 for n in nodes}
    adjacency = defaultdict(list)

    for edge in edges:
        adjacency[edge["source_node_id"]].append(edge["target_node_id"])
        in_degree[edge["target_node_id"]] += 1

    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
    order = []

    while queue:
        nid = queue.popleft()
        order.append(nid)
        for neighbor in adjacency[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(nodes):
        raise ValueError("Workflow graph contains a cycle.")

    return order
```

---

## Checkpoint System — `core/checkpoint.py`

Each node's output is cached after successful execution. The cache key is a hash of the node's `block_type_id`, `parameters`, and the cache keys of all its inputs.

This means: if you change a parameter on an upstream node, all downstream nodes are automatically invalidated.

```python
# core/checkpoint.py
import hashlib
import json
import pickle
from pathlib import Path
from neurodata.types import NeuroData

CACHE_DIR = Path(".synapchart_cache")

def _make_key(node_id: str, block_type_id: str, parameters: dict, input_keys: list[str]) -> str:
    """Deterministic hash of node identity + parameters + upstream keys."""
    payload = json.dumps({
        "block_type_id": block_type_id,
        "parameters": parameters,
        "input_keys": sorted(input_keys),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]

def has_cache(cache_key: str) -> bool:
    return (CACHE_DIR / f"{cache_key}.pkl").exists()

def load_cache(cache_key: str) -> dict[str, NeuroData]:
    with open(CACHE_DIR / f"{cache_key}.pkl", "rb") as f:
        return pickle.load(f)

def save_cache(cache_key: str, outputs: dict[str, NeuroData]) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    with open(CACHE_DIR / f"{cache_key}.pkl", "wb") as f:
        pickle.dump(outputs, f)

def clear_cache(node_id: str = None) -> None:
    """Clear all cache, or (future) cache for a specific node."""
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.pkl"):
            f.unlink()
```

### Cache invalidation rules
- A node's cache is valid if its `cache_key` matches a stored file
- Changing any parameter of a node changes its `cache_key`, invalidating it and all downstream nodes
- Deleting or replacing an input file invalidates the loader node (because the file path parameter changes)
- The user can manually clear a node's cache via right-click → "Clear cache for this node" on the canvas (calls `POST /api/pipeline/clear-cache` with a `node_id`)

---

## Execution Engine — `core/executor.py`

```python
# core/executor.py
import asyncio
from typing import AsyncGenerator
from core.graph import topological_sort
from core.checkpoint import _make_key, has_cache, load_cache, save_cache
from core.block_registry import get_block
from core.validator import validate_workflow

class PipelineExecutor:
    """
    Executes a SynapChart workflow.

    Usage:
        executor = PipelineExecutor(workflow)
        async for log_message in executor.run(use_cache=True):
            # stream log_message to WebSocket clients
    """

    def __init__(self, workflow: dict):
        self.workflow = workflow
        self.nodes = {n["node_id"]: n for n in workflow["nodes"]}
        self.edges = workflow["edges"]
        self._outputs: dict[str, dict] = {}   # node_id -> {port_id -> NeuroData}
        self._cache_keys: dict[str, str] = {} # node_id -> cache_key
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    async def run(self, use_cache: bool = True) -> AsyncGenerator[dict, None]:
        """
        Full pipeline run. Yields log message dicts.
        Log message shape: { "level": "info"|"warning"|"error", "node_id": str|None, "message": str }
        """
        errors = validate_workflow(self.workflow)
        if errors:
            for e in errors:
                yield {"level": "error", "node_id": None, "message": e}
            return

        try:
            order = topological_sort(list(self.nodes.values()), self.edges)
        except ValueError as e:
            yield {"level": "error", "node_id": None, "message": str(e)}
            return

        for node_id in order:
            if self._stop_requested:
                yield {"level": "info", "node_id": None, "message": "Pipeline stopped by user."}
                return
            async for msg in self._execute_node(node_id, use_cache):
                yield msg

        yield {"level": "info", "node_id": None, "message": "Pipeline complete."}

    async def step(self, node_id: str) -> AsyncGenerator[dict, None]:
        """
        Execute a single node. All inputs must be available from cache.
        """
        # Load cached outputs of all predecessor nodes into self._outputs
        for edge in self.edges:
            if edge["target_node_id"] == node_id:
                pred_id = edge["source_node_id"]
                if pred_id not in self._outputs:
                    # Try to load from cache
                    pred_node = self.nodes[pred_id]
                    input_keys = self._get_input_cache_keys(pred_id)
                    key = _make_key(pred_id, pred_node["block_type_id"], pred_node["parameters"], input_keys)
                    if has_cache(key):
                        self._outputs[pred_id] = load_cache(key)
                        self._cache_keys[pred_id] = key
                    else:
                        yield {"level": "error", "node_id": node_id,
                               "message": f"Cannot step: upstream node '{pred_id}' has no cached result. Run the full pipeline first."}
                        return

        async for msg in self._execute_node(node_id, use_cache=False):
            yield msg

    async def _execute_node(self, node_id: str, use_cache: bool) -> AsyncGenerator[dict, None]:
        node = self.nodes[node_id]
        block_type_id = node["block_type_id"]
        parameters = node.get("parameters", {})

        input_keys = self._get_input_cache_keys(node_id)
        cache_key = _make_key(node_id, block_type_id, parameters, input_keys)
        self._cache_keys[node_id] = cache_key

        if use_cache and has_cache(cache_key):
            self._outputs[node_id] = load_cache(cache_key)
            yield {"level": "info", "node_id": node_id, "message": f"Loaded from cache.", "status": "cached"}
            return

        yield {"level": "info", "node_id": node_id, "message": f"Running...", "status": "running"}

        inputs = self._collect_inputs(node_id)
        block = get_block(block_type_id)

        try:
            # Run in a thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            outputs = await loop.run_in_executor(None, block.run, inputs, parameters)
        except Exception as e:
            yield {"level": "error", "node_id": node_id, "message": str(e), "status": "error"}
            return

        self._outputs[node_id] = outputs
        save_cache(cache_key, outputs)
        yield {"level": "info", "node_id": node_id, "message": "Done.", "status": "done"}

    def _collect_inputs(self, node_id: str) -> dict:
        """Gather all input port values for a node from upstream outputs."""
        inputs = {}
        for edge in self.edges:
            if edge["target_node_id"] == node_id:
                src_outputs = self._outputs.get(edge["source_node_id"], {})
                inputs[edge["target_port_id"]] = src_outputs.get(edge["source_port_id"])
        return inputs

    def _get_input_cache_keys(self, node_id: str) -> list[str]:
        """Get the cache keys of all direct predecessor nodes."""
        keys = []
        for edge in self.edges:
            if edge["target_node_id"] == node_id:
                pred_id = edge["source_node_id"]
                if pred_id in self._cache_keys:
                    keys.append(self._cache_keys[pred_id])
        return keys
```

---

## WebSocket Log Streaming

The `/api/pipeline/logs` WebSocket endpoint streams execution messages as JSON objects to the frontend. The frontend listens on this socket and updates node status badges in real time.

### Log message schema

```json
{
  "level": "info",        // "info" | "warning" | "error"
  "node_id": "bandpass_filter_a3f2",  // null for pipeline-level messages
  "message": "Running...",
  "status": "running"    // "running" | "done" | "cached" | "error" | null
}
```

The frontend maps `status` values to node badge colors:

| status | Badge |
|---|---|
| `"running"` | Blue spinner |
| `"done"` | Green check |
| `"cached"` | Yellow bookmark |
| `"error"` | Red X |
| null | No change |

### FastAPI WebSocket handler

```python
# api/pipeline.py (excerpt)
from fastapi import WebSocket
from core.executor import PipelineExecutor

active_executor: PipelineExecutor | None = None

@router.websocket("/logs")
async def logs_ws(websocket: WebSocket):
    await websocket.accept()
    # The executor is set by the /run endpoint; this socket just listens
    # Use an asyncio.Queue to bridge the run endpoint and this socket
    ...
```

Implementation note: use a module-level `asyncio.Queue` to bridge between the `POST /run` HTTP handler (which starts the executor) and the WebSocket handler (which streams messages to the client). Both handlers share the same queue.

---

## Execution State Machine

```
idle
 │
 ├─[POST /run]──────────► running
 │                           │
 │                    ┌──────┴──────┐
 │                    │             │
 │              [all nodes done]  [POST /stop or exception]
 │                    │             │
 │                   done         error / stopped
 │                    │             │
 └────────────────────┴─────────────┘
                  [new /run request resets state]
```

Only one pipeline run is permitted at a time in v1. A `POST /run` while status is `running` returns HTTP 409 with error code `already_running`.
