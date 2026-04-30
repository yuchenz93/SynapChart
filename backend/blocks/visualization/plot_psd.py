
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotPsd(BlockBase):
    """Plot power spectral density."""

    block_type_id = "plot_psd"
    display_name = "Plot PSD"
    category = "Visualization"
    description = "Plots power spectral density."

    inputs = [
        PortDefinition("psd", "NeuroData[raw_signal]", "PSD data (frequencies in timestamps, power in array)."),
    ]
    outputs: list[PortDefinition] = []
    parameters = [
        ParameterDefinition("title", "str", "Power Spectral Density", "Plot title."),
        ParameterDefinition("log_scale", "bool", True, "Use log scale on the y-axis."),
        ParameterDefinition("show_on_run", "bool", True, "Open a pop-out window when executed."),
        ParameterDefinition("save_path", "str", "", "Path to save the PNG. Empty = no save."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        psd: NeuroData = inputs["psd"]
        title = str(parameters.get("title", "Power Spectral Density"))
        log_scale = bool(parameters.get("log_scale", True))
        show = bool(parameters.get("show_on_run", True))
        save_path = str(parameters.get("save_path", ""))

        freqs = psd.timestamps if psd.timestamps is not None else np.arange(len(psd.array))
        power = psd.array

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(freqs, power, lw=1.0)
        if log_scale:
            ax.set_yscale("log")
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("Power")
        ax.set_title(title)
        fig.tight_layout()

        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
