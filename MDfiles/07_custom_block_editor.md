# SynapChart — Doc 07: Custom Block Editor

## Overview

This document specifies the "New Block" feature, which allows users to create
custom blocks directly within the SynapChart UI without editing any project files
manually. Custom blocks behave identically to built-in blocks once created — they
appear in the side panel, can be dragged to the canvas, saved in workflows, and
shared as block packages.

The design principle is: the user only writes the scientific logic. The system
handles all boilerplate.

---

## User Flow

```
Side panel → "New Block" button
    │
    ▼
Block creation wizard (3-step modal)
    │
    ├── Step 1: Metadata
    │       block name, category, description
    │
    ├── Step 2: Ports & Parameters
    │       define inputs, outputs, parameters
    │       (dynamic table, add/remove rows)
    │
    └── Step 3: Source code
            Monaco editor, pre-filled template
            "Test run" button → shows errors inline
            "Save block" → registers + appears in side panel
```

---

## UI — Side Panel Addition

Add a "New block" button at the top of the side panel, above the search box.

```
┌─────────────────────────┐
│  [+ New block]          │  ← new button
│  🔍 Search blocks...    │
│                         │
│  ▼ Data I/O             │
│  ▼ Behavior             │
│  ...                    │
└─────────────────────────┘
```

Clicking "New block" opens the block creation wizard as a full-screen modal.
Existing blocks in the side panel can be opened for editing via right-click →
"Edit block definition" — this opens the same wizard pre-filled with the block's
current definition.

---

## UI — Block Creation Wizard

### Step 1: Metadata

Simple form fields:

| Field | Type | Notes |
|---|---|---|
| Block name | Text input | Shown on canvas. E.g. "Theta cycle detector" |
| block_type_id | Text input | Auto-generated from name (snake_case), editable. Must be unique. |
| Category | Dropdown + "New category" option | Selects from existing categories or creates one |
| Description | Textarea | One or two sentences shown in side panel tooltip |

Auto-generation rule for `block_type_id`: take the block name, lowercase it,
replace spaces and special characters with underscores.
Example: "Theta cycle detector" → `theta_cycle_detector`

Show a warning if the `block_type_id` already exists in the registry.

---

### Step 2: Ports and Parameters

Three dynamic tables — Inputs, Outputs, Parameters. Each table has an "Add row"
button and a delete button per row.

**Inputs table:**

| Column | Type | Notes |
|---|---|---|
| Port name | Text input | snake_case, e.g. `signal` |
| Data type | Dropdown | See type dropdown options below |
| Description | Text input | Short label |
| Required | Checkbox | Default: checked |

**Outputs table:**

Same columns as Inputs except no "Required" column.

**Parameters table:**

| Column | Type | Notes |
|---|---|---|
| Parameter name | Text input | snake_case, e.g. `threshold` |
| Data type | Dropdown | str / float / int / bool / enum |
| Default value | Text input | Must be valid for the chosen type |
| Description | Text input | Shown as tooltip in the block popup |

**Data type dropdown options (for ports):**

```
NeuroData[raw_signal]
NeuroData[lfp]
NeuroData[spike_times]
NeuroData[spike_matrix]
NeuroData[position]
NeuroData[tuning_curve]
NeuroData[decoded]
NeuroData[any]
float
int
str
bool
```

**Data type dropdown options (for parameters):**

```
str
float
int
bool
enum  ← reveals a second field: "comma-separated values"
```

---

### Step 3: Source Code

A Monaco editor pre-filled with a template generated from the port/parameter
definitions entered in Step 2.

#### Template generation

When the user arrives at Step 3, the editor is pre-filled with a template based
on what they entered in Step 2. For example, if the user defined:
- Input: `signal` (NeuroData[lfp])
- Input: `threshold` (float)  
- Output: `events` (NeuroData[raw_signal])
- Parameter: `min_duration_sec` (float, default 0.05)

The pre-filled template is:

```python
# Available inputs:
#   inputs['signal']    → NeuroData[lfp]
#   inputs['threshold'] → float
#
# Available parameters:
#   parameters['min_duration_sec'] → float (default: 0.05)
#
# Your outputs must match:
#   'events' → NeuroData[raw_signal]
#
# Import numpy and scipy freely. Other packages must be in requirements.txt.

import numpy as np

# --- Write your logic below ---

signal_array = inputs['signal'].array
sr = inputs['signal'].sampling_rate

# example: threshold crossing detection
above = signal_array > inputs['threshold']
events_array = above.astype(float)

# --- Return your outputs ---
return {
    'events': NeuroData(
        data_type='raw_signal',
        array=events_array,
        sampling_rate=sr,
    )
}
```

The user only edits the logic between the comment markers. They do not write a
class definition, `__init__`, or `run()` signature — the system adds all of that.

#### "Test run" button

Runs the block with automatically generated dummy data based on port types:

| Port type | Dummy data generated |
|---|---|
| `NeuroData[raw_signal]` / `NeuroData[lfp]` | 1000-sample sine wave, sr=1000 |
| `NeuroData[spike_times]` | 50 random timestamps over 10 seconds |
| `NeuroData[spike_matrix]` | 10×100 random int array |
| `NeuroData[position]` | 300-sample linear ramp, sr=30 |
| `NeuroData[any]` | 100-sample random array |
| `float` / `int` | 1.0 / 1 |
| `str` | `"test"` |

Test run results appear below the editor:
- On success: green banner "Test passed. Output types: events → NeuroData[raw_signal]"
- On Python error: red banner with the traceback, line numbers highlighted in editor
- On type mismatch (returned wrong type): yellow warning "Output 'events' expected
  NeuroData[raw_signal] but got NeuroData[lfp]. This may cause connection errors."

#### "Save block" button

Saves the block and closes the wizard. The new block immediately appears in the
side panel under its chosen category. See backend section for persistence details.

---

## Backend — Code Generation

When the user saves a custom block, the backend generates a complete `BlockBase`
subclass from the wizard inputs and the user's source code snippet.

### Generated class structure

Given the example above, the backend generates:

```python
# backend/blocks/user/theta_cycle_detector.py
# Auto-generated by SynapChart custom block editor.
# You can edit this file directly — changes take effect on server restart.

from blocks.base import BlockBase, PortDefinition, ParameterDefinition
from neurodata.types import NeuroData
import numpy as np


class ThetaCycleDetector(BlockBase):

    block_type_id = "theta_cycle_detector"
    display_name = "Theta cycle detector"
    category = "LFP / EEG"
    description = "Detects theta cycles from LFP signal using threshold crossing."

    inputs = [
        PortDefinition(port_id="signal",    data_type="NeuroData[lfp]",  description="LFP signal", required=True),
        PortDefinition(port_id="threshold", data_type="float",            description="",           required=True),
    ]
    outputs = [
        PortDefinition(port_id="events", data_type="NeuroData[raw_signal]", description=""),
    ]
    parameters = [
        ParameterDefinition(name="min_duration_sec", data_type="float", default=0.05, description=""),
    ]

    def run(self, inputs, parameters):
        # --- User code start ---
        import numpy as np

        signal_array = inputs['signal'].array
        sr = inputs['signal'].sampling_rate

        above = signal_array > inputs['threshold']
        events_array = above.astype(float)

        return {
            'events': NeuroData(
                data_type='raw_signal',
                array=events_array,
                sampling_rate=sr,
            )
        }
        # --- User code end ---
```

### Code generation rules

- Class name: convert `block_type_id` to PascalCase
  (`theta_cycle_detector` → `ThetaCycleDetector`)
- The user's snippet is inserted verbatim inside the `run()` method, indented
  correctly
- `import numpy as np` and `from neurodata.types import NeuroData` are always
  available inside `run()` — injected at the top of the method
- No other imports are injected; user must include any other imports inside their
  snippet

---

## Backend — New API Endpoints

Add these endpoints to `api/blocks.py`:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/blocks/create` | Generate, save, and register a new custom block |
| `PUT` | `/api/blocks/{block_type_id}` | Update an existing custom block |
| `DELETE` | `/api/blocks/{block_type_id}` | Delete a custom block |
| `POST` | `/api/blocks/test-run` | Run a block snippet with dummy data, return result or error |

### `POST /api/blocks/create` request body

```json
{
  "block_type_id": "theta_cycle_detector",
  "display_name": "Theta cycle detector",
  "category": "LFP / EEG",
  "description": "Detects theta cycles from LFP signal.",
  "inputs": [
    { "port_id": "signal",    "data_type": "NeuroData[lfp]", "description": "", "required": true },
    { "port_id": "threshold", "data_type": "float",           "description": "", "required": true }
  ],
  "outputs": [
    { "port_id": "events", "data_type": "NeuroData[raw_signal]", "description": "" }
  ],
  "parameters": [
    { "name": "min_duration_sec", "data_type": "float", "default": 0.05, "description": "" }
  ],
  "source_snippet": "import numpy as np\n\nsignal_array = inputs['signal'].array\n..."
}
```

### `POST /api/blocks/test-run` request body

```json
{
  "source_snippet": "...",
  "inputs": [ { "port_id": "signal", "data_type": "NeuroData[lfp]" } ],
  "outputs": [ { "port_id": "events", "data_type": "NeuroData[raw_signal]" } ],
  "parameters": [ { "name": "min_duration_sec", "data_type": "float", "default": 0.05 } ]
}
```

Response on success:
```json
{
  "status": "ok",
  "output_types": { "events": "NeuroData[raw_signal]" },
  "execution_time_ms": 12
}
```

Response on error:
```json
{
  "status": "error",
  "error_type": "python_exception",
  "message": "NameError: name 'signall' is not defined",
  "traceback": "...",
  "line_number": 4
}
```

---

## Backend — Persistence

Custom blocks are saved as `.py` files in `backend/blocks/user/`. This folder is
created automatically if it does not exist.

```
backend/blocks/user/
├── __init__.py               ← empty, created automatically
├── theta_cycle_detector.py   ← generated file
└── my_other_block.py
```

The existing block auto-discovery in `core/block_registry.py` already walks all
subfolders of `backend/blocks/` — no changes needed there. Custom blocks in
`blocks/user/` are discovered and registered automatically on server startup.

When a user edits a custom block via the wizard and saves, the `.py` file is
overwritten and the block is re-registered in memory immediately (no server
restart required).

When a user deletes a custom block, the `.py` file is deleted and the block is
removed from the registry. Any workflow using that block will show an error on
the affected nodes.

Custom blocks in `blocks/user/` should be committed to git — they are part of
the user's project, not generated build artifacts.

---

## Security Note

User-supplied code runs directly on the local machine with full Python privileges.
This is intentional and appropriate for a local research tool — the same trust
model as a Jupyter notebook. Do not expose the `/api/blocks/create` or
`/api/blocks/test-run` endpoints on a public network (`--host 0.0.0.0`) without
adding authentication first.

Add a warning comment in `cli.py` if the user starts with `--host 0.0.0.0`:

```python
if host == "0.0.0.0":
    click.echo("WARNING: Running with --host 0.0.0.0 exposes the server to your "
               "network. Custom block execution runs arbitrary Python code. Only "
               "do this on a trusted network.", err=True)
```
