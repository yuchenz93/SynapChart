
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotSignal(BlockBase):
    """Plot one or more continuous signals as time series."""

    block_type_id = "plot_signal"
    display_name = "Plot Signal"
    category = "Visualization"
    description = "Plots one or more continuous signals as time series."

    inputs = [
        PortDefinition("signal", "NeuroData[raw_signal]", "Signal to plot."),
    ]
    outputs: list[PortDefinition] = []
    parameters = [
        ParameterDefinition("title", "str", "Signal", "Plot title."),
        ParameterDefinition("show_on_run", "bool", True, "Open a pop-out window when executed."),
        ParameterDefinition("save_path", "str", "", "Path to save the PNG. Empty = no save."),
        ParameterDefinition("t_start", "float", 0.0, "Start time to display (seconds)."),
        ParameterDefinition("t_stop", "float", -1.0, "Stop time to display (seconds). -1 = full signal."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        signal: NeuroData = inputs["signal"]
        title = str(parameters.get("title", "Signal"))
        show = bool(parameters.get("show_on_run", True))
        save_path = str(parameters.get("save_path", ""))
        t_start = float(parameters.get("t_start", 0.0))
        t_stop = float(parameters.get("t_stop", -1.0))

        arr = signal.array
        sr = signal.sampling_rate or 1000.0
        if signal.timestamps is not None:
            time = signal.timestamps
        else:
            time = np.arange(arr.shape[0]) / sr

        mask = (time >= t_start) & (time <= (t_stop if t_stop >= 0 else time[-1]))
        time = time[mask]
        arr = arr[mask] if arr.ndim == 1 else arr[mask, :]

        fig, ax = plt.subplots(figsize=(10, 3))
        if arr.ndim == 1:
            ax.plot(time, arr, lw=0.8)
        else:
            for ch in range(arr.shape[1]):
                ax.plot(time, arr[:, ch], lw=0.8, label=f"ch{ch}")
            ax.legend(fontsize=8)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Amplitude")
        ax.set_title(title)
        fig.tight_layout()

        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
