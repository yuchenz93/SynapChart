
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotRaster(BlockBase):
    """Plot a spike raster for one or more units."""

    block_type_id = "plot_raster"
    display_name = "Plot Raster"
    category = "Visualization"
    description = "Plots a spike raster for one or more units."

    inputs = [
        PortDefinition("spikes", "NeuroData[spike_times]", "Spike timestamps (seconds)."),
    ]
    outputs: list[PortDefinition] = []
    parameters = [
        ParameterDefinition("title", "str", "Spike Raster", "Plot title."),
        ParameterDefinition("t_start", "float", 0.0, "Start time (seconds)."),
        ParameterDefinition("t_stop", "float", -1.0, "Stop time (seconds). -1 = full range."),
        ParameterDefinition("show_on_run", "bool", True, "Open a pop-out window when executed."),
        ParameterDefinition("save_path", "str", "", "Path to save the PNG. Empty = no save."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        spikes: NeuroData = inputs["spikes"]
        title = str(parameters.get("title", "Spike Raster"))
        t_start = float(parameters.get("t_start", 0.0))
        t_stop = float(parameters.get("t_stop", -1.0))
        show = bool(parameters.get("show_on_run", True))
        save_path = str(parameters.get("save_path", ""))

        times = spikes.array
        if t_stop >= 0:
            times = times[(times >= t_start) & (times <= t_stop)]
        else:
            times = times[times >= t_start]

        fig, ax = plt.subplots(figsize=(10, 2))
        ax.eventplot(times, lineoffsets=0, linelengths=0.8, linewidths=0.5, color="black")
        ax.set_xlabel("Time (s)")
        ax.set_yticks([])
        ax.set_title(title)
        fig.tight_layout()

        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
