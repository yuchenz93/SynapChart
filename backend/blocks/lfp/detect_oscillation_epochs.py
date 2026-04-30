
from __future__ import annotations

from typing import Any

import numpy as np
from scipy.signal import hilbert

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class DetectOscillationEpochs(BlockBase):
    """Detect epochs where instantaneous power exceeds a z-score threshold."""

    block_type_id = "detect_oscillation_epochs"
    display_name = "Detect Oscillation Epochs"
    category = "LFP / EEG"
    description = "Detects epochs where instantaneous power exceeds a threshold (e.g. theta bouts)."

    inputs = [
        PortDefinition("signal", "NeuroData[lfp]", "Band-limited signal."),
    ]
    outputs = [
        PortDefinition("epochs", "NeuroData[raw_signal]", "N×2 array of [start, stop] timestamps in seconds."),
    ]
    parameters = [
        ParameterDefinition("threshold_sd", "float", 2.0, "Threshold in standard deviations above mean envelope."),
        ParameterDefinition("min_duration_sec", "float", 0.1, "Minimum epoch duration in seconds."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        signal: NeuroData = inputs["signal"]
        threshold_sd = float(parameters.get("threshold_sd", 2.0))
        min_dur = float(parameters.get("min_duration_sec", 0.1))
        sr = signal.sampling_rate or 1000.0

        arr = signal.array
        if arr.ndim > 1:
            arr = arr[:, 0]

        envelope = np.abs(hilbert(arr))
        z = (envelope - envelope.mean()) / (envelope.std() + np.finfo(float).eps)
        above = z > threshold_sd

        # Find contiguous runs of True
        padded = np.concatenate([[False], above, [False]])
        diff = np.diff(padded.astype(int))
        starts = np.where(diff == 1)[0]
        stops  = np.where(diff == -1)[0]

        min_samples = int(min_dur * sr)
        valid = (stops - starts) >= min_samples

        if signal.timestamps is not None:
            ts = signal.timestamps
            epoch_times = np.column_stack([ts[starts[valid]], ts[stops[valid] - 1]])
        else:
            epoch_times = np.column_stack([starts[valid] / sr, (stops[valid] - 1) / sr])

        return {
            "epochs": NeuroData(
                data_type="raw_signal",
                array=epoch_times,
                metadata={"n_epochs": int(valid.sum())},
            )
        }
