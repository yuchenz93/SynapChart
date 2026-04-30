
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotDecodedPosterior(BlockBase):
    """Plot the decoded posterior probability matrix as a heatmap over time."""

    block_type_id = "plot_decoded_posterior"
    display_name = "Plot Decoded Posterior"
    category = "Visualization"
    description = "Plots the decoded posterior probability matrix as a heatmap over time."

    inputs = [
        PortDefinition("decoded", "NeuroData[decoded]", "Posterior matrix (positions × time bins)."),
    ]
    outputs: list[PortDefinition] = []
    parameters = [
        ParameterDefinition("title", "str", "Decoded Posterior", "Plot title."),
        ParameterDefinition("show_on_run", "bool", True, "Open a pop-out window when executed."),
        ParameterDefinition("save_path", "str", "", "Path to save the PNG. Empty = no save."),
        ParameterDefinition("colormap", "str", "viridis", "Matplotlib colormap name."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        decoded: NeuroData = inputs["decoded"]
        title = str(parameters.get("title", "Decoded Posterior"))
        show = bool(parameters.get("show_on_run", True))
        save_path = str(parameters.get("save_path", ""))
        cmap = str(parameters.get("colormap", "viridis"))

        posterior = decoded.array   # shape: (n_positions, n_time_bins)
        time_bins = decoded.timestamps if decoded.timestamps is not None else np.arange(posterior.shape[1])

        fig, ax = plt.subplots(figsize=(10, 4))
        im = ax.imshow(
            posterior,
            aspect="auto",
            origin="lower",
            extent=[float(time_bins[0]), float(time_bins[-1]), 0, posterior.shape[0]],
            cmap=cmap,
            vmin=0,
        )
        fig.colorbar(im, ax=ax, label="Probability")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Position bin")
        ax.set_title(title)
        fig.tight_layout()

        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
