
from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class ComputeTuningCurve(BlockBase):
    """Compute a 1-D tuning curve (firing rate as a function of a behavioral variable)."""

    block_type_id = "compute_tuning_curve"
    display_name = "Compute Tuning Curve"
    category = "Spikes"
    description = "Computes 1-D tuning curve (firing rate as a function of position or another variable)."

    inputs = [
        PortDefinition("spikes", "NeuroData[spike_times]", "1-D spike timestamps (seconds)."),
        PortDefinition("variable", "NeuroData[position]", "Behavioral variable sampled at a regular rate (e.g. linearized position)."),
    ]
    outputs = [
        PortDefinition("tuning_curve", "NeuroData[tuning_curve]", "Firing rate per bin (Hz)."),
    ]
    parameters = [
        ParameterDefinition("n_bins", "int", 50, "Number of spatial/variable bins."),
        ParameterDefinition("min_occupancy_sec", "float", 0.1, "Minimum occupancy per bin (seconds) to include in output."),
        ParameterDefinition("smooth_sigma", "float", 1.0, "Gaussian smoothing sigma in bins (0 = no smoothing)."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        spikes: NeuroData = inputs["spikes"]
        variable: NeuroData = inputs["variable"]

        spike_times = spikes.array
        var_values = variable.array if variable.array.ndim == 1 else variable.array[:, 0]
        var_times = variable.timestamps
        sr = variable.sampling_rate or 30.0

        if var_times is None:
            var_times = np.arange(len(var_values)) / sr

        n_bins = int(parameters.get("n_bins", 50))
        min_occ = float(parameters.get("min_occupancy_sec", 0.1))
        sigma = float(parameters.get("smooth_sigma", 1.0))

        var_min, var_max = var_values.min(), var_values.max()
        bins = np.linspace(var_min, var_max, n_bins + 1)
        bin_centers = (bins[:-1] + bins[1:]) / 2.0

        # Interpolate variable at spike times
        spike_var = np.interp(spike_times, var_times, var_values,
                              left=np.nan, right=np.nan)
        valid = ~np.isnan(spike_var)

        spike_counts, _ = np.histogram(spike_var[valid], bins=bins)
        dt = 1.0 / sr
        occupancy, _ = np.histogram(var_values, bins=bins)
        occupancy_sec = occupancy * dt

        with np.errstate(invalid="ignore", divide="ignore"):
            rate = np.where(occupancy_sec >= min_occ, spike_counts / occupancy_sec, 0.0)

        if sigma > 0:
            from scipy.ndimage import gaussian_filter1d
            rate = gaussian_filter1d(rate, sigma=sigma)

        return {
            "tuning_curve": NeuroData(
                data_type="tuning_curve",
                array=rate,
                timestamps=bin_centers,
                metadata={"n_bins": n_bins, "var_min": float(var_min), "var_max": float(var_max)},
            )
        }
