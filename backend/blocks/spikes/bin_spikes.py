
from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class BinSpikes(BlockBase):
    """Convert spike times to a binned spike count matrix."""

    block_type_id = "bin_spikes"
    display_name = "Bin Spikes"
    category = "Spikes"
    description = "Converts spike times to a binned spike count matrix."

    inputs = [
        PortDefinition("spikes", "NeuroData[spike_times]", "1-D spike timestamps (seconds)."),
    ]
    outputs = [
        PortDefinition("spike_matrix", "NeuroData[spike_matrix]", "1-D spike count array (N_bins,)."),
    ]
    parameters = [
        ParameterDefinition("bin_size_sec", "float", 0.02, "Bin width in seconds."),
        ParameterDefinition("t_start", "float", 0.0, "Start time in seconds."),
        ParameterDefinition("t_stop", "float", -1.0, "Stop time in seconds. -1 uses the last spike time."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        spikes: NeuroData = inputs["spikes"]
        spike_times = spikes.array
        bin_size = float(parameters.get("bin_size_sec", 0.02))
        t_start = float(parameters.get("t_start", 0.0))
        t_stop = float(parameters.get("t_stop", -1.0))

        if t_stop < 0:
            t_stop = float(spike_times.max()) + bin_size if len(spike_times) > 0 else 1.0

        bins = np.arange(t_start, t_stop + bin_size, bin_size)
        counts, _ = np.histogram(spike_times, bins=bins)
        bin_centers = (bins[:-1] + bins[1:]) / 2.0

        return {
            "spike_matrix": NeuroData(
                data_type="spike_matrix",
                array=counts.reshape(1, -1),   # shape (1, N_bins) for single unit
                sampling_rate=1.0 / bin_size,
                timestamps=bin_centers,
                metadata={"bin_size_sec": bin_size, "t_start": t_start, "t_stop": t_stop},
            )
        }
