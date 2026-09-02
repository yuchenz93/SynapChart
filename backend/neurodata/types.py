"""NeuroData type system for SynapChart pipelines."""


from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


# NeuroData.data_type is a free-form **semantic role** tag (e.g. "lfp",
# "spike_times"). Compatibility is derived structurally + by role in
# neurodata/port_types.py (see docs/specs/12_port_type_system_v2.md); there is no
# longer a fixed registry of valid types.


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
