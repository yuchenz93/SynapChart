
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotPhasePrecession(BlockBase):
    """Plot spike phase vs. position (theta phase precession scatter plot)."""

    block_type_id = "plot_phase_precession"
    display_name = "Plot Phase Precession"
    category = "Visualization"
    description = "Plots spike phase vs. position (the theta phase precession scatter plot)."

    inputs = [
        PortDefinition("spikes", "NeuroData[spike_times]", "Spike timestamps (seconds)."),
        PortDefinition("phase", "NeuroData[raw_signal]", "Instantaneous LFP phase (radians)."),
        PortDefinition("position", "NeuroData[position]", "Linearized or 2-D position."),
    ]
    outputs: list[PortDefinition] = []
    parameters = [
        ParameterDefinition("title", "str", "Phase Precession", "Plot title."),
        ParameterDefinition("show_on_run", "bool", True, "Open a pop-out window when executed."),
        ParameterDefinition("save_path", "str", "", "Path to save the PNG. Empty = no save."),
        ParameterDefinition("position_range", "str", "auto", "Position range 'auto' or 'min,max'."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        spikes: NeuroData = inputs["spikes"]
        phase_nd: NeuroData = inputs["phase"]
        position: NeuroData = inputs["position"]

        title = str(parameters.get("title", "Phase Precession"))
        show = bool(parameters.get("show_on_run", True))
        save_path = str(parameters.get("save_path", ""))

        spike_times = spikes.array
        phase_arr = phase_nd.array if phase_nd.array.ndim == 1 else phase_nd.array[:, 0]
        pos_arr = position.array if position.array.ndim == 1 else position.array[:, 0]

        sr_phase = phase_nd.sampling_rate or 1000.0
        sr_pos = position.sampling_rate or 30.0

        phase_times = phase_nd.timestamps if phase_nd.timestamps is not None else np.arange(len(phase_arr)) / sr_phase
        pos_times = position.timestamps if position.timestamps is not None else np.arange(len(pos_arr)) / sr_pos

        spike_phases = np.interp(spike_times, phase_times, phase_arr, left=np.nan, right=np.nan)
        spike_pos = np.interp(spike_times, pos_times, pos_arr, left=np.nan, right=np.nan)

        valid = ~(np.isnan(spike_phases) | np.isnan(spike_pos))
        spike_phases = spike_phases[valid]
        spike_pos = spike_pos[valid]

        # Pearson correlation between phase and position
        if len(spike_phases) >= 2:
            corr_r = float(np.corrcoef(spike_phases, spike_pos)[0, 1])
            full_title = f"{title}  (r = {corr_r:.3f})"
        else:
            full_title = title

        fig, ax = plt.subplots(figsize=(7, 5))
        ax.scatter(spike_pos, spike_phases, s=4, alpha=0.5, c="steelblue", rasterized=True)
        ax.set_xlabel("Position")
        ax.set_ylabel("Phase (rad)")
        ax.set_yticks([-np.pi, 0, np.pi])
        ax.set_yticklabels(["-π", "0", "π"])
        ax.set_title(full_title)
        fig.tight_layout()

        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
