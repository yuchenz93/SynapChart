"""Plot per-state population tuning curves from compute_tuning_curves_1d."""


from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotTuningCurves1d(BlockBase):
    """Plot rate maps for selected states side-by-side."""

    block_type_id = "plot_tuning_curves_1d"
    display_name  = "Plot Tuning Curves 1D"
    category      = "maze1d / Visualization"
    description   = (
        "Shows a grid of firing-rate vs position curves for every cell in the "
        "selected states.  Each column is a state; each row is a cell."
    )

    inputs = [
        PortDefinition("tuning_curves", "NeuroData[tuning_curves_1d]",
                       "Per-state rate maps from compute_tuning_curves_1d."),
    ]
    outputs: list = []
    parameters = [
        ParameterDefinition("state_keys",    "str",  "",
                            "Comma-separated state names to display.  Empty = all states."),
        ParameterDefinition("cell_filter",   "enum:all,pyramidal,interneuron", "pyramidal",
                            "Which cells to plot."),
        ParameterDefinition("max_cells",     "int",  20,
                            "Maximum number of cells to show (sorted by peak rate)."),
        ParameterDefinition("colormap",      "str",  "hot",    "Matplotlib colormap."),
        ParameterDefinition("close_all",     "bool", True,     "Close existing figures."),
        ParameterDefinition("show_on_run",   "bool", True,     "Show in viz panel."),
        ParameterDefinition("save_path",     "str",  "",       "PNG save path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        tc: NeuroData = inputs["tuning_curves"]

        keys_str    = str(parameters.get("state_keys",  "")).strip()
        cell_filt   = str(parameters.get("cell_filter", "pyramidal"))
        max_cells   = int(parameters.get("max_cells",   20))
        cmap        = str(parameters.get("colormap",    "hot"))
        close_all   = bool(parameters.get("close_all",  True))
        show        = bool(parameters.get("show_on_run",True))
        save_path   = str(parameters.get("save_path",   ""))

        if close_all:
            plt.close("all")

        rate_maps_all = tc.metadata.get("rate_maps", {})
        all_keys      = tc.metadata.get("state_keys", list(rate_maps_all.keys()))
        selected_keys = [k.strip() for k in keys_str.split(",") if k.strip()] \
                        if keys_str else all_keys
        selected_keys = [k for k in selected_keys if k in rate_maps_all]

        if not selected_keys:
            fig, ax = plt.subplots(figsize=(5, 3))
            ax.text(0.5, 0.5, "No states selected.", ha="center", va="center",
                    transform=ax.transAxes)
            viz = save_and_encode(fig, save_path, show)
            return {"_viz": viz} if viz else {}

        bin_centers = np.array(tc.metadata.get("bin_centers",
                                                tc.timestamps if tc.timestamps is not None
                                                else np.arange(tc.array.shape[1])))
        cell_ids    = tc.metadata.get("cell_ids", [])
        pyr_set     = set(str(c) for c in tc.metadata.get("pyr_ids", []))
        int_set     = set(str(c) for c in tc.metadata.get("int_ids", []))

        # Cell selection
        if cell_filt == "pyramidal":
            sel_cells = [c for c in cell_ids if str(c) in pyr_set]
        elif cell_filt == "interneuron":
            sel_cells = [c for c in cell_ids if str(c) in int_set]
        else:
            sel_cells = list(cell_ids)

        # Sort by peak rate (first state) and limit count
        first_maps = rate_maps_all[selected_keys[0]]
        cell_idx   = [cell_ids.index(c) if c in cell_ids else -1 for c in sel_cells]
        cell_idx   = [i for i in cell_idx if i >= 0]
        peak_rates = [float(first_maps[i].max()) for i in cell_idx]
        sorted_idx = [cell_idx[j] for j in np.argsort(peak_rates)[::-1]][:max_cells]
        n_cells    = len(sorted_idx)

        if n_cells == 0:
            fig, ax = plt.subplots(figsize=(5, 3))
            ax.text(0.5, 0.5, "No cells match filter.", ha="center", va="center",
                    transform=ax.transAxes)
            viz = save_and_encode(fig, save_path, show)
            return {"_viz": viz} if viz else {}

        n_cols = len(selected_keys)
        n_rows = n_cells
        fig, axes = plt.subplots(n_rows, n_cols,
                                  figsize=(n_cols * 3.5, n_rows * 1.2 + 0.8),
                                  squeeze=False)

        for col, sname in enumerate(selected_keys):
            maps = rate_maps_all[sname]
            axes[0][col].set_title(sname, fontsize=11, pad=4)
            for row, ci in enumerate(sorted_idx):
                ax = axes[row][col]
                ax.plot(bin_centers, maps[ci], linewidth=1.2, color="#3b82f6")
                ax.set_xlim(bin_centers[0], bin_centers[-1])
                ax.set_ylim(bottom=0)
                ax.tick_params(labelsize=7)
                ax.spines[["top", "right"]].set_visible(False)
                if col == 0:
                    cid_label = str(cell_ids[ci])
                    ax.set_ylabel(f"c{cid_label}", fontsize=7, rotation=0,
                                  labelpad=20, va="center")
                if row < n_rows - 1:
                    ax.set_xticklabels([])

        for ax in axes[-1]:
            ax.set_xlabel("Position (cm)", fontsize=10)

        fig.suptitle(f"Tuning curves — {cell_filt} ({n_cells} cells)", fontsize=13, y=1.01)
        fig.tight_layout()
        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
