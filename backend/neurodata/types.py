"""NeuroData type system for SynapChart pipelines."""


from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


# Valid values for NeuroData.data_type.
# Extend this tuple and update the validator compatibility table to add new types.
REGISTERED_DATA_TYPES: tuple[str, ...] = (
    "raw_signal",    # Unprocessed continuous signal (any modality)
    "lfp",           # Local field potential (filtered raw signal)
    "spike_times",   # 1-D array of spike timestamps for a single unit
    "spike_matrix",  # 2-D array: units × time bins
    "position",      # Animal position data (x, y, timestamps)
    "tuning_curve",  # Place field or tuning curve (bins × firing rate)
    "decoded",       # Posterior probability matrix from a decoder
    "any",           # Accepts any NeuroData type (use sparingly)
    # ── CRCNS / population types ─────────────────────────────────────────────
    "multi_spike_times",       # Spike times for many cells; cell IDs in metadata
    "epochs",                  # Session epoch boundaries (MazeEpoch, PREEpoch …)
    "tuning_curves_population",# (n_cells × n_bins) firing-rate maps for all cells
    "place_fields",            # Per-cell place-field boundaries and properties
    "phase_precession",        # Per-cell θ-phase vs position regression results
    "theta_cycles",            # (N × 2) array of theta cycle [t_start, t_end]
    "theta_sequence",          # Averaged look-ahead/behind sequence matrix
    "laps",                    # Directional running bouts: (N × 3) [t_start, t_end, direction]
)


@dataclass
class NeuroData:
    """The universal data envelope for SynapChart pipelines.

    All block outputs must be NeuroData instances.
    All block inputs receive NeuroData instances.

    Attributes:
        data_type:     One of the registered type strings (e.g. "lfp", "spike_times").
                       Used by the port validator.
        array:         The primary numpy array payload.
        sampling_rate: Samples per second. None if not applicable.
        timestamps:    1-D numpy array of timestamps (seconds). None if not applicable.
        channel_names: List of channel label strings. None if not applicable.
        metadata:      Arbitrary dict for any additional annotations.
                       Blocks should document what keys they add.
    """

    data_type: str
    array: np.ndarray
    sampling_rate: float | None = None
    timestamps: np.ndarray | None = None
    channel_names: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # External library blocks define their own data_type strings.
        # We no longer hard-reject unknown types here; the port-level validator
        # (core/validator.py) handles type compatibility and already allows
        # unknown types through for external libraries.
        pass
