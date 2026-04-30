# SynapChart — Doc 01: Backend Core

## Overview

The backend is a FastAPI application. It serves three purposes:
1. Expose REST and WebSocket endpoints to the frontend
2. Maintain the block registry (available block types)
3. Delegate to the execution engine and checkpoint system (see Doc 04)

This document covers the FastAPI app structure, all API endpoints, the port validator, and the NeuroData type system.

---

## Entry Point: `backend/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import pipeline, blocks, files

app = FastAPI(title="SynapChart Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline.router, prefix="/api/pipeline")
app.include_router(blocks.router, prefix="/api/blocks")
app.include_router(files.router, prefix="/api/files")
```

---

## API Endpoints

### Pipeline endpoints — `api/pipeline.py`

All pipeline endpoints operate on a workflow JSON object sent in the request body (see Doc 03 for schema).

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/pipeline/run` | Run entire pipeline from scratch (ignores checkpoints) |
| `POST` | `/api/pipeline/run-from-cache` | Run pipeline, loading cached results where available |
| `POST` | `/api/pipeline/step` | Execute a single named node by `node_id` |
| `POST` | `/api/pipeline/stop` | Interrupt a running pipeline |
| `GET` | `/api/pipeline/status` | Return current execution state |
| `WS` | `/api/pipeline/logs` | WebSocket stream of live execution logs |

#### Request body for run endpoints

```json
{
  "workflow": { ... },      // full workflow JSON (see Doc 03)
  "run_options": {
    "use_cache": true,       // whether to load from checkpoints
    "target_node_id": null   // if set, run only up to this node
  }
}
```

#### Response for run endpoints

```json
{
  "run_id": "uuid-string",
  "status": "started"
}
```

Progress and logs are streamed over the WebSocket. Final results per node are retrievable via the checkpoint API (Doc 04).

---

### Block registry endpoints — `api/blocks.py`

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/blocks/` | List all registered blocks (grouped by category) |
| `GET` | `/api/blocks/{block_type_id}` | Get full definition of one block type |
| `POST` | `/api/blocks/validate-connection` | Check if two ports are compatible |
| `POST` | `/api/blocks/register-custom` | Register a new custom block from source code |

#### `GET /api/blocks/` response shape

```json
{
  "categories": [
    {
      "name": "Data I/O",
      "blocks": [
        {
          "block_type_id": "load_npy",
          "display_name": "Load .npy file",
          "category": "Data I/O",
          "description": "Loads a numpy .npy or .npz file from disk.",
          "inputs": [],
          "outputs": [
            { "port_id": "data", "type": "NeuroData", "description": "Loaded array" }
          ],
          "parameters": [
            { "name": "file_path", "type": "str", "default": "", "description": "Absolute path to the .npy file" }
          ]
        }
      ]
    }
  ]
}
```

---

### File endpoints — `api/files.py`

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/files/save` | Save workflow JSON to a file path on disk |
| `POST` | `/api/files/load` | Load workflow JSON from a file path on disk |
| `GET` | `/api/files/templates` | List available template workflows |
| `GET` | `/api/files/templates/{name}` | Load a named template workflow |

---

## Port Validator — `core/validator.py`

The validator checks whether a connection between two ports is allowed. It is called both when the user draws a connection on the canvas and again at pipeline execution time.

### Validation rules

1. **Type compatibility:** The output port type must be compatible with the input port type. See the compatibility table below.
2. **Direction:** A connection must go from an output port to an input port — never output-to-output or input-to-input.
3. **Multiplicity:** An input port may only have one incoming connection. An output port may connect to multiple inputs.

### NeuroData type compatibility table

| Output type | Accepted by input type |
|---|---|
| `NeuroData[raw_signal]` | `NeuroData[raw_signal]`, `NeuroData[any]` |
| `NeuroData[lfp]` | `NeuroData[lfp]`, `NeuroData[raw_signal]`, `NeuroData[any]` |
| `NeuroData[spike_times]` | `NeuroData[spike_times]`, `NeuroData[any]` |
| `NeuroData[spike_matrix]` | `NeuroData[spike_matrix]`, `NeuroData[any]` |
| `NeuroData[position]` | `NeuroData[position]`, `NeuroData[any]` |
| `NeuroData[tuning_curve]` | `NeuroData[tuning_curve]`, `NeuroData[any]` |
| `NeuroData[decoded]` | `NeuroData[decoded]`, `NeuroData[any]` |
| `NeuroData[any]` | `NeuroData[any]` only (warns on all others) |
| `float` | `float` |
| `int` | `int`, `float` |
| `str` | `str` |

### Validator API

```python
# core/validator.py

def validate_connection(
    output_port_type: str,
    input_port_type: str,
) -> tuple[bool, str]:
    """
    Returns (is_valid, message).
    message is empty string on success, human-readable reason on failure.
    """
```

```python
def validate_workflow(workflow: dict) -> list[str]:
    """
    Validates all connections in a workflow JSON.
    Returns a list of warning/error strings (empty list = all valid).
    """
```

---

## NeuroData Type System — `neurodata/types.py`

All data passed between blocks is wrapped in a `NeuroData` object. This ensures that metadata travels with the data and that the port validator has enough information to catch mismatches.

### NeuroData class

```python
from dataclasses import dataclass, field
from typing import Any
import numpy as np

@dataclass
class NeuroData:
    """
    The universal data envelope for SynapChart pipelines.

    All block outputs must be NeuroData instances.
    All block inputs receive NeuroData instances.

    Attributes:
        data_type:    One of the registered type strings (e.g. "lfp", "spike_times").
                      Used by the port validator.
        array:        The primary numpy array payload.
        sampling_rate: Samples per second. None if not applicable.
        timestamps:   1-D numpy array of timestamps (seconds). None if not applicable.
        channel_names: List of channel label strings. None if not applicable.
        metadata:     Arbitrary dict for any additional annotations.
                      Blocks should document what keys they add.
    """
    data_type: str
    array: np.ndarray
    sampling_rate: float | None = None
    timestamps: np.ndarray | None = None
    channel_names: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### Registered data_type strings

These are the valid values for `NeuroData.data_type`. The port validator uses these strings.

| data_type string | Description |
|---|---|
| `"raw_signal"` | Unprocessed continuous signal (any modality) |
| `"lfp"` | Local field potential (filtered raw signal) |
| `"spike_times"` | 1-D array of spike timestamps for a single unit |
| `"spike_matrix"` | 2-D array: units × time bins |
| `"position"` | Animal position data (x, y, timestamps) |
| `"tuning_curve"` | Place field or tuning curve (bins × firing rate) |
| `"decoded"` | Posterior probability matrix from a decoder |
| `"any"` | Accepts any NeuroData type (use sparingly) |

New data types can be added by appending to this table and updating the validator compatibility table. No other changes are required.

---

## Error Handling

All API endpoints return standard HTTP status codes. Error bodies follow this shape:

```json
{
  "error": "short_error_code",
  "message": "Human-readable description of what went wrong.",
  "details": {}
}
```

Common error codes:

| Code | HTTP status | Meaning |
|---|---|---|
| `invalid_workflow` | 422 | Workflow JSON failed schema validation |
| `type_mismatch` | 422 | A connection has incompatible port types |
| `block_not_found` | 404 | A block_type_id in the workflow is not registered |
| `execution_error` | 500 | A block raised an exception during execution |
| `already_running` | 409 | A pipeline is already running (only one at a time in v1) |
