# SynapChart — Doc 03: Block System

## Overview

This document defines:
1. The `BlockBase` class that all blocks inherit from
2. The workflow JSON schema
3. The block package format (for sharing)
4. The built-in block library (categories and specific blocks for v1)

---

## BlockBase Class — `backend/blocks/base.py`

Every block in SynapChart is a Python class that inherits from `BlockBase`.

```python
# backend/blocks/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from neurodata.types import NeuroData


@dataclass
class PortDefinition:
    port_id: str
    data_type: str          # e.g. "NeuroData[lfp]", "float", "str"
    description: str
    required: bool = True


@dataclass
class ParameterDefinition:
    name: str
    data_type: str          # "str", "float", "int", "bool", or "enum:val1,val2,val3"
    default: Any
    description: str


class BlockBase(ABC):
    """
    Base class for all SynapChart blocks.

    Subclasses must define:
      - block_type_id: unique string identifier (snake_case)
      - display_name: human-readable name shown on the canvas
      - category: one of the registered category strings
      - description: one or two sentences describing what this block does
      - inputs: list of PortDefinition
      - outputs: list of PortDefinition
      - parameters: list of ParameterDefinition

    Subclasses must implement:
      - run(self, inputs: dict, parameters: dict) -> dict
    """

    block_type_id: str = ""
    display_name: str = ""
    category: str = ""
    description: str = ""
    inputs: list[PortDefinition] = []
    outputs: list[PortDefinition] = []
    parameters: list[ParameterDefinition] = []

    @abstractmethod
    def run(self, inputs: dict[str, NeuroData | Any], parameters: dict[str, Any]) -> dict[str, NeuroData | Any]:
        """
        Execute this block.

        Args:
            inputs:     dict mapping port_id -> NeuroData (or primitive) value
            parameters: dict mapping parameter name -> current value

        Returns:
            dict mapping output port_id -> NeuroData (or primitive) value
        """
        ...

    def to_definition(self) -> dict:
        """Serialize block metadata to the JSON definition format used by the API."""
        return {
            "block_type_id": self.block_type_id,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "inputs": [vars(p) for p in self.inputs],
            "outputs": [vars(p) for p in self.outputs],
            "parameters": [vars(p) for p in self.parameters],
        }
```

---

## Workflow JSON Schema

A workflow file is a single JSON object with the following structure.

```json
{
  "schema_version": "1.0",
  "name": "My analysis pipeline",
  "description": "Optional free-text description.",
  "created_at": "2025-01-01T00:00:00Z",
  "modified_at": "2025-01-01T00:00:00Z",
  "nodes": [
    {
      "node_id": "load_npy_a1b2",
      "block_type_id": "load_npy",
      "position": { "x": 100, "y": 200 },
      "parameters": {
        "file_path": "/data/lfp_recording.npy"
      },
      "user_notes": "Optional per-node annotation visible in the editor."
    }
  ],
  "edges": [
    {
      "edge_id": "e_001",
      "source_node_id": "load_npy_a1b2",
      "source_port_id": "data",
      "target_node_id": "bandpass_filter_c3d4",
      "target_port_id": "signal"
    }
  ]
}
```

### Schema rules
- `node_id` must be unique within the workflow
- `edge_id` must be unique within the workflow
- `block_type_id` must match a registered block
- Each input port may have at most one incoming edge
- The graph must be a DAG (no cycles)
- `position` is used for canvas layout only and does not affect execution

---

## Block Package Format (Registry-Ready)

A block package is a directory (or zip file) with the following structure. This format is designed so that a future community registry can accept package uploads without requiring structural changes.

```
my_block_package/
├── manifest.json       # Package metadata
├── blocks/
│   ├── my_block_1.py   # One file per block class
│   └── my_block_2.py
└── requirements.txt    # Optional: extra pip dependencies
```

### `manifest.json`

```json
{
  "package_id": "my_lab_lfp_blocks",
  "version": "0.1.0",
  "display_name": "My Lab LFP Blocks",
  "description": "Custom LFP analysis blocks from the Smith Lab.",
  "author": "Smith Lab, University of X",
  "synapchart_min_version": "1.0",
  "blocks": ["my_block_1.MyBlock1", "my_block_2.MyBlock2"]
}
```

The `blocks` field lists Python module paths (relative to the package root) for each block class.

---

## Built-in Block Library (v1)

The following blocks are implemented as part of SynapChart v1. Each block is described with its `block_type_id`, inputs, outputs, and parameters. Implementation files live in `backend/blocks/{category}/`.

---

### Category: Data I/O — `backend/blocks/io/`

#### `load_npy`
Loads a `.npy` or `.npz` file from disk.
- **Inputs:** none
- **Outputs:** `data` → `NeuroData[raw_signal]`
- **Parameters:** `file_path` (str), `sampling_rate` (float, default 1000.0), `data_type_override` (enum: raw_signal/lfp/spike_times/position, default raw_signal)

#### `load_csv`
Loads a CSV file. First column is treated as timestamps if `has_timestamps` is true.
- **Inputs:** none
- **Outputs:** `data` → `NeuroData[raw_signal]`
- **Parameters:** `file_path` (str), `has_timestamps` (bool, default True), `sampling_rate` (float, default 1000.0)

#### `save_npy`
Saves a NeuroData array to disk as `.npy`.
- **Inputs:** `data` → `NeuroData[any]`
- **Outputs:** none
- **Parameters:** `file_path` (str), `overwrite` (bool, default False)

#### `export_csv`
Exports a NeuroData array to CSV.
- **Inputs:** `data` → `NeuroData[any]`
- **Outputs:** none
- **Parameters:** `file_path` (str), `include_timestamps` (bool, default True)

---

### Category: Behavior Processing — `backend/blocks/behavior/`

#### `load_position`
Loads x/y position data and timestamps from file.
- **Inputs:** none
- **Outputs:** `position` → `NeuroData[position]`
- **Parameters:** `file_path` (str), `x_col` (int, default 0), `y_col` (int, default 1), `time_col` (int, default 2), `sampling_rate` (float, default 30.0)

#### `smooth_position`
Applies Gaussian smoothing to position data.
- **Inputs:** `position` → `NeuroData[position]`
- **Outputs:** `position` → `NeuroData[position]`
- **Parameters:** `sigma_seconds` (float, default 0.1)

#### `compute_speed`
Computes instantaneous running speed from position.
- **Inputs:** `position` → `NeuroData[position]`
- **Outputs:** `speed` → `NeuroData[raw_signal]`
- **Parameters:** none

#### `linearize_position`
Projects 2-D position onto a 1-D linear track.
- **Inputs:** `position` → `NeuroData[position]`
- **Outputs:** `linear_pos` → `NeuroData[position]`
- **Parameters:** `method` (enum: pca/manual_axis, default pca)

---

### Category: LFP / EEG Processing — `backend/blocks/lfp/`

#### `bandpass_filter`
Zero-phase Butterworth bandpass filter.
- **Inputs:** `signal` → `NeuroData[raw_signal]`
- **Outputs:** `filtered` → `NeuroData[lfp]`
- **Parameters:** `low_hz` (float, default 4.0), `high_hz` (float, default 12.0), `order` (int, default 4)

#### `extract_phase`
Extracts instantaneous phase via Hilbert transform.
- **Inputs:** `signal` → `NeuroData[lfp]`
- **Outputs:** `phase` → `NeuroData[raw_signal]`
- **Parameters:** none

#### `compute_psd`
Computes power spectral density using Welch's method.
- **Inputs:** `signal` → `NeuroData[raw_signal]`
- **Outputs:** `psd` → `NeuroData[raw_signal]`
- **Parameters:** `window_seconds` (float, default 1.0), `overlap` (float, default 0.5)

#### `detect_oscillation_epochs`
Detects epochs where instantaneous power exceeds a threshold (e.g. theta bouts).
- **Inputs:** `signal` → `NeuroData[lfp]`
- **Outputs:** `epochs` → `NeuroData[raw_signal]`  (N×2 array of [start, stop] timestamps)
- **Parameters:** `threshold_sd` (float, default 2.0), `min_duration_sec` (float, default 0.1)

#### `select_reference_channel`
Selects a single channel from a multi-channel signal.
- **Inputs:** `signal` → `NeuroData[raw_signal]`
- **Outputs:** `channel` → `NeuroData[raw_signal]`
- **Parameters:** `channel_index` (int, default 0)

---

### Category: Spike Processing — `backend/blocks/spikes/`

#### `load_spike_times`
Loads spike times for one or more units from a file.
- **Inputs:** none
- **Outputs:** `spikes` → `NeuroData[spike_times]`
- **Parameters:** `file_path` (str), `unit_index` (int, default 0, use -1 for all units)

#### `bin_spikes`
Converts spike times to a binned spike count matrix.
- **Inputs:** `spikes` → `NeuroData[spike_times]`
- **Outputs:** `spike_matrix` → `NeuroData[spike_matrix]`
- **Parameters:** `bin_size_sec` (float, default 0.02), `t_start` (float, default 0.0), `t_stop` (float, default -1.0, -1 means use data end)

#### `compute_firing_rate`
Computes smoothed firing rate from spike times using a Gaussian kernel.
- **Inputs:** `spikes` → `NeuroData[spike_times]`
- **Outputs:** `rate` → `NeuroData[raw_signal]`
- **Parameters:** `sigma_sec` (float, default 0.05), `bin_size_sec` (float, default 0.01)

#### `compute_tuning_curve`
Computes 1-D tuning curve (firing rate as a function of position or another variable).
- **Inputs:** `spikes` → `NeuroData[spike_times]`, `variable` → `NeuroData[position]`
- **Outputs:** `tuning_curve` → `NeuroData[tuning_curve]`
- **Parameters:** `n_bins` (int, default 50), `min_occupancy_sec` (float, default 0.1), `smooth_sigma` (float, default 1.0)

#### `spike_phase_coupling`
Computes spike-phase histogram: spike phases relative to an LFP oscillation.
- **Inputs:** `spikes` → `NeuroData[spike_times]`, `phase` → `NeuroData[raw_signal]`
- **Outputs:** `phase_hist` → `NeuroData[raw_signal]`
- **Parameters:** `n_bins` (int, default 36)

---

### Category: Visualization — `backend/blocks/visualization/`

All visualization blocks use matplotlib. They produce a PNG saved to disk and optionally displayed in a pop-out window. See Doc 02 (VizWindow) for display behavior.

#### `plot_signal`
Plots one or more continuous signals as time series.
- **Inputs:** `signal` → `NeuroData[raw_signal]`
- **Outputs:** none
- **Parameters:** `title` (str, default "Signal"), `show_on_run` (bool, default True), `save_path` (str, default ""), `t_start` (float, default 0.0), `t_stop` (float, default -1.0)

#### `plot_psd`
Plots power spectral density.
- **Inputs:** `psd` → `NeuroData[raw_signal]`
- **Outputs:** none
- **Parameters:** `title` (str), `log_scale` (bool, default True), `show_on_run` (bool, default True), `save_path` (str, default "")

#### `plot_raster`
Plots a spike raster for one or more units.
- **Inputs:** `spikes` → `NeuroData[spike_times]`
- **Outputs:** none
- **Parameters:** `title` (str), `t_start` (float), `t_stop` (float), `show_on_run` (bool, default True), `save_path` (str, default "")

#### `plot_tuning_curve`
Plots a 1-D tuning curve (place field or other).
- **Inputs:** `tuning_curve` → `NeuroData[tuning_curve]`
- **Outputs:** none
- **Parameters:** `title` (str), `x_label` (str, default "Position (cm)"), `y_label` (str, default "Firing rate (Hz)"), `show_on_run` (bool, default True), `save_path` (str, default "")

#### `plot_phase_precession`
Plots spike phase vs. position (the theta phase precession scatter plot).
- **Inputs:** `spikes` → `NeuroData[spike_times]`, `phase` → `NeuroData[raw_signal]`, `position` → `NeuroData[position]`
- **Outputs:** none
- **Parameters:** `title` (str), `show_on_run` (bool, default True), `save_path` (str, default ""), `position_range` (str, default "auto")

#### `plot_decoded_posterior`
Plots the decoded posterior probability matrix as a heatmap over time.
- **Inputs:** `decoded` → `NeuroData[decoded]`
- **Outputs:** none
- **Parameters:** `title` (str), `show_on_run` (bool, default True), `save_path` (str, default ""), `colormap` (str, default "viridis")

---

## Block Registration

On startup, the FastAPI backend auto-discovers and registers all built-in blocks. The registration logic lives in `core/block_registry.py`.

```python
# core/block_registry.py

import importlib
import pkgutil
import blocks
from blocks.base import BlockBase

_registry: dict[str, BlockBase] = {}

def discover_blocks():
    """Walk the blocks/ package and register all BlockBase subclasses."""
    for finder, name, ispkg in pkgutil.walk_packages(blocks.__path__, prefix="blocks."):
        module = importlib.import_module(name)
        for attr in vars(module).values():
            if isinstance(attr, type) and issubclass(attr, BlockBase) and attr is not BlockBase:
                instance = attr()
                _registry[instance.block_type_id] = instance

def get_block(block_type_id: str) -> BlockBase:
    return _registry[block_type_id]

def all_blocks() -> dict[str, BlockBase]:
    return dict(_registry)
```

Custom blocks registered via `POST /api/blocks/register-custom` are added to `_registry` at runtime and do not persist across server restarts (v1). Persistence of custom blocks is a v2 feature.
