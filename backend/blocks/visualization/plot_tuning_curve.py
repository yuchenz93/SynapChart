
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotTuningCurve(BlockBase):
    """Plot a 1-D tuning curve (place field or other)."""

    block_type_id = "plot_tuning_curve"
    display_name = "Plot Tuning Curve"
    category = "Visualization"
    description = "Plots a 1-D tuning curve (place field or other)."

    inputs = [
        PortDefinition("tuning_curve", "NeuroData[tuning_curve]", "Tuning curve (bins × firing rate)."),
    ]
    outputs: list[PortDefinition] = []
    parameters = [
        ParameterDefinition("title", "str", "Tuning Curve", "Plot title."),
        ParameterDefinition("x_label", "str", "Position (cm)", "X-axis label."),
        ParameterDefinition("y_label", "str", "Firing rate (Hz)", "Y-axis label."),
        ParameterDefinition("show_on_run", "bool", True, "Open a pop-out window when executed."),
        ParameterDefinition("save_path", "str", "", "Path to save the PNG. Empty = no save."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        tc: NeuroData = inputs["tuning_curve"]
        title = str(parameters.get("title", "Tuning Curve"))
        x_label = str(parameters.get("x_label", "Position (cm)"))
        y_label = str(parameters.get("y_label", "Firing rate (Hz)"))
        show = bool(parameters.get("show_on_run", True))
        save_path = str(parameters.get("save_path", ""))

        bins = tc.timestamps if tc.timestamps is not None else np.arange(len(tc.array))

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(bins, tc.array, lw=1.5)
        ax.fill_between(bins, tc.array, alpha=0.3)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.set_title(title)
        fig.tight_layout()

        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
