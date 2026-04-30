
from __future__ import annotations

from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter1d

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class ComputeFiringRate(BlockBase):
    """Compute a smoothed firing rate from spike times using a Gaussian kernel."""

    block_type_id = "compute_firing_rate"
    display_name = "Compute Firing Rate"
    category = "Spikes"
    description = "Computes smoothed firing rate from spike times using a Gaussian kernel."

    inputs = [
        PortDefinition("spikes", "NeuroData[spike_times]", "1-D spike timestamps (seconds)."),
    ]
    outputs = [
        PortDefinition("rate", "NeuroData[raw_signal]", "Smoothed firing rate in Hz."),
    ]
    parameters = [
        ParameterDefinition("sigma_sec", "float", 0.05, "Gaussian kernel standard deviation in seconds."),
        ParameterDefinition("bin_size_sec", "float", 0.01, "Bin size for the intermediate count histogram."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        spikes: NeuroData = inputs["spikes"]
        spike_times = spikes.array
        bin_size = float(parameters.get("bin_size_sec", 0.01))
        sigma_sec = float(parameters.get("sigma_sec", 0.05))

        if len(spike_times) == 0:
            return {"rate": NeuroData(data_type="raw_signal", array=np.array([]), sampling_rate=1.0 / bin_size)}

        t_start = float(spike_times.min())
        t_stop = float(spike_times.max()) + bin_size
        bins = np.arange(t_start, t_stop + bin_size, bin_size)
        counts, _ = np.histogram(spike_times, bins=bins)
        bin_centers = (bins[:-1] + bins[1:]) / 2.0

        rate_raw = counts / bin_size   # convert counts to Hz
        sigma_bins = sigma_sec / bin_size
        rate_smooth = gaussian_filter1d(rate_raw.astype(float), sigma=sigma_bins)

        return {
            "rate": NeuroData(
                data_type="raw_signal",
                array=rate_smooth,
                sampling_rate=1.0 / bin_size,
                timestamps=bin_centers,
                metadata={"units": "Hz", "sigma_sec": sigma_sec},
            )
        }
