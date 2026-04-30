
from __future__ import annotations

from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter1d

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class SmoothPosition(BlockBase):
    """Apply Gaussian smoothing to x/y position data."""

    block_type_id = "smooth_position"
    display_name = "Smooth Position"
    category = "Behavior"
    description = "Applies Gaussian smoothing to position data."

    inputs = [
        PortDefinition("position", "NeuroData[position]", "Raw position data (N × 2)."),
    ]
    outputs = [
        PortDefinition("position", "NeuroData[position]", "Smoothed position data (N × 2)."),
    ]
    parameters = [
        ParameterDefinition("sigma_seconds", "float", 0.1, "Gaussian kernel width in seconds."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        pos: NeuroData = inputs["position"]
        sigma_sec = float(parameters.get("sigma_seconds", 0.1))
        sr = pos.sampling_rate or 30.0
        sigma_samples = sigma_sec * sr

        arr = pos.array
        if arr.ndim == 1 or (arr.ndim == 2 and arr.shape[1] == 1):
            smoothed = gaussian_filter1d(arr.flatten(), sigma=sigma_samples)
        else:
            smoothed = np.column_stack([
                gaussian_filter1d(arr[:, 0], sigma=sigma_samples),
                gaussian_filter1d(arr[:, 1], sigma=sigma_samples),
            ])
        return {
            "position": NeuroData(
                data_type="position",
                array=smoothed,
                sampling_rate=pos.sampling_rate,
                timestamps=pos.timestamps,
                metadata={**pos.metadata, "smoothed": True, "sigma_seconds": sigma_sec},
            )
        }
