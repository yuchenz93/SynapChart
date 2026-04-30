
from __future__ import annotations

from typing import Any

import numpy as np
from scipy.signal import hilbert

from blocks.base import BlockBase, PortDefinition
from neurodata.types import NeuroData


class ExtractPhase(BlockBase):
    """Extract instantaneous phase via the Hilbert transform."""

    block_type_id = "extract_phase"
    display_name = "Extract Phase"
    category = "LFP / EEG"
    description = "Extracts instantaneous phase via the Hilbert transform."

    inputs = [
        PortDefinition("signal", "NeuroData[lfp]", "Band-limited signal (e.g. theta-filtered LFP)."),
    ]
    outputs = [
        PortDefinition("phase", "NeuroData[raw_signal]", "Instantaneous phase in radians (−π to π)."),
    ]
    parameters = []

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        signal: NeuroData = inputs["signal"]
        analytic = hilbert(signal.array, axis=0)
        phase = np.angle(analytic)

        return {
            "phase": NeuroData(
                data_type="raw_signal",
                array=phase,
                sampling_rate=signal.sampling_rate,
                timestamps=signal.timestamps,
                channel_names=signal.channel_names,
                metadata={**signal.metadata, "phase_radians": True},
            )
        }
