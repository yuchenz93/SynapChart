
from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class SpikePhaseCoupling(BlockBase):
    """Compute a spike-phase histogram for LFP phase coupling analysis."""

    block_type_id = "spike_phase_coupling"
    display_name = "Spike-Phase Coupling"
    category = "Spikes"
    description = "Computes spike-phase histogram: spike phases relative to an LFP oscillation."

    inputs = [
        PortDefinition("spikes", "NeuroData[spike_times]", "1-D spike timestamps (seconds)."),
        PortDefinition("phase", "NeuroData[raw_signal]", "Instantaneous phase signal in radians."),
    ]
    outputs = [
        PortDefinition("phase_hist", "NeuroData[raw_signal]", "Phase histogram (counts per bin)."),
    ]
    parameters = [
        ParameterDefinition("n_bins", "int", 36, "Number of phase bins (default 36 = 10° per bin)."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        spikes: NeuroData = inputs["spikes"]
        phase_nd: NeuroData = inputs["phase"]

        spike_times = spikes.array
        phase_arr = phase_nd.array if phase_nd.array.ndim == 1 else phase_nd.array[:, 0]
        sr = phase_nd.sampling_rate or 1000.0

        # Build a time axis for the phase signal
        if phase_nd.timestamps is not None:
            phase_times = phase_nd.timestamps
        else:
            phase_times = np.arange(len(phase_arr)) / sr

        # Interpolate phase at each spike time
        spike_phases = np.interp(
            spike_times, phase_times, phase_arr,
            left=np.nan, right=np.nan,
        )
        valid = ~np.isnan(spike_phases)

        n_bins = int(parameters.get("n_bins", 36))
        edges = np.linspace(-np.pi, np.pi, n_bins + 1)
        counts, _ = np.histogram(spike_phases[valid], bins=edges)
        bin_centers = (edges[:-1] + edges[1:]) / 2.0

        return {
            "phase_hist": NeuroData(
                data_type="raw_signal",
                array=counts.astype(float),
                timestamps=bin_centers,
                metadata={"n_spikes": int(valid.sum()), "n_bins": n_bins, "phase_units": "radians"},
            )
        }
