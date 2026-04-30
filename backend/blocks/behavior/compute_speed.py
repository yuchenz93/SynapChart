
from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, PortDefinition
from neurodata.types import NeuroData


class ComputeSpeed(BlockBase):
    """Compute instantaneous running speed from x/y position data."""

    block_type_id = "compute_speed"
    display_name = "Compute Speed"
    category = "Behavior"
    description = "Computes instantaneous running speed from position."

    inputs = [
        PortDefinition("position", "NeuroData[position]", "Position data (N × 2)."),
    ]
    outputs = [
        PortDefinition("speed", "NeuroData[raw_signal]", "Speed in cm/s (or units/s), length N-1."),
    ]
    parameters = []

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        pos: NeuroData = inputs["position"]
        xy = pos.array
        dx = np.diff(xy[:, 0])
        dy = np.diff(xy[:, 1])

        if pos.timestamps is not None:
            dt = np.diff(pos.timestamps)
        else:
            sr = pos.sampling_rate or 30.0
            dt = np.full(len(dx), 1.0 / sr)

        speed = np.sqrt(dx ** 2 + dy ** 2) / np.where(dt > 0, dt, np.finfo(float).eps)
        ts_out = pos.timestamps[:-1] if pos.timestamps is not None else None

        return {
            "speed": NeuroData(
                data_type="raw_signal",
                array=speed,
                sampling_rate=pos.sampling_rate,
                timestamps=ts_out,
            )
        }
