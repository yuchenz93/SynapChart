"""Plot tuning curves for all cells in a population.

Cells are laid out in a grid.  Place fields (if provided) are highlighted.
Set ``close_all`` to True (default) to call ``plt.close('all')`` before
plotting — recommended when visualising many cells to prevent window explosion.
"""


from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotPopulationTuningCurves(BlockBase):
    """Plot tuning-curve grid for all cells in a population."""

    block_type_id = "plot_population_tuning_curves"
    display_name  = "Plot Population Tuning Curves"
    category      = "Visualization"
    description   = (
        "Plots a grid of firing-rate-vs-position tuning curves for all cells "
        "in a tuning_curves_population NeuroData. Optionally overlays place "
        "field boundaries."
    )

    inputs = [
        PortDefinition("tuning_curves", "NeuroData[tuning_curves_population]",
                       "Population tuning curves (n_cells × n_bins)."),
        PortDefinition("place_fields",  "NeuroData[place_fields]",
                       "Optional: place field boundaries for shading.",
                       required=False),
    ]
    outputs: list[PortDefinition] = []
    parameters = [
        ParameterDefinition("cells_per_row", "int",  10,   "Subplots per row."),
        ParameterDefinition("max_cells",     "int",  120,  "Maximum cells to plot (0 = all)."),
        ParameterDefinition("cell_filter",
                            "enum:all,pyramidal,interneuron", "pyramidal",
                            "Which cell type to display."),
        ParameterDefinition("close_all",    "bool", True,
                            "Call plt.close('all') before plotting to avoid window accumulation."),
        ParameterDefinition("show_on_run",  "bool", True,  "Emit figure to the viz panel."),
        ParameterDefinition("save_path",    "str",  "",    "PNG save path. Empty = no save."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        tc: NeuroData = inputs["tuning_curves"]
        pf            = inputs.get("place_fields")

        cells_per_row = int(parameters.get("cells_per_row", 10))
        max_cells     = int(parameters.get("max_cells",     120))
        cell_filt     = str(parameters.get("cell_filter",   "pyramidal"))
        close_all     = bool(parameters.get("close_all",    True))
        show          = bool(parameters.get("show_on_run",  True))
        save_path     = str(parameters.get("save_path",     ""))

        if close_all:
            plt.close("all")

        rate_maps   = tc.array
        bin_centers = tc.timestamps if tc.timestamps is not None else np.arange(rate_maps.shape[1])
        cell_ids    = tc.metadata.get("cell_ids", list(range(rate_maps.shape[0])))
        pyr_ids_set = set(str(c) for c in tc.metadata.get("pyr_ids", []))
        int_ids_set = set(str(c) for c in tc.metadata.get("int_ids", []))

        # Filter by cell type
        filtered_idx = []
        for i, cid in enumerate(cell_ids):
            key = str(cid)
            if cell_filt == "pyramidal" and key not in pyr_ids_set:
                continue
            if cell_filt == "interneuron" and key not in int_ids_set:
                continue
            filtered_idx.append(i)

        if max_cells > 0:
            filtered_idx = filtered_idx[:max_cells]

        n_cells = len(filtered_idx)
        if n_cells == 0:
            fig, ax = plt.subplots()
            ax.text(0.5, 0.5, "No cells to display.", ha="center", va="center")
            viz = save_and_encode(fig, save_path, show)
            return {"_viz": viz} if viz else {}

        n_rows = max(1, int(np.ceil(n_cells / cells_per_row)))
        n_cols = min(n_cells, cells_per_row)

        fig, axes = plt.subplots(
            n_rows, n_cols,
            figsize=(max(n_cols * 1.4, 6), max(n_rows * 1.2, 3)),
            squeeze=False,
        )

        fields_meta = pf.metadata.get("fields", {}) if pf is not None else {}

        for plot_i, cell_i in enumerate(filtered_idx):
            row, col = divmod(plot_i, cells_per_row)
            ax  = axes[row][col]
            cid = cell_ids[cell_i]
            rate = rate_maps[cell_i]

            ax.fill_between(bin_centers, 0, rate, alpha=0.6,
                            color="#3b82f6" if str(cid) in pyr_ids_set else "#f97316")
            ax.plot(bin_centers, rate, color="#1e40af" if str(cid) in pyr_ids_set else "#c2410c",
                    linewidth=0.8)

            # Shade place fields
            for fld in fields_meta.get(str(cid), []):
                ax.axvspan(fld["start_pos"], fld["end_pos"],
                           alpha=0.15, color="red", zorder=0)

            ax.set_xlim(bin_centers[0], bin_centers[-1])
            ax.set_ylim(0, None)
            ax.set_title(str(cid), fontsize=6, pad=1)
            ax.tick_params(labelsize=5)
            ax.spines[["top", "right"]].set_visible(False)

        # Hide unused axes
        for plot_i in range(n_cells, n_rows * n_cols):
            row, col = divmod(plot_i, cells_per_row)
            axes[row][col].set_visible(False)

        label = {"all": "all cells", "pyramidal": "pyr", "interneuron": "int"}[cell_filt]
        fig.suptitle(f"Tuning curves — {label} ({n_cells} cells)", fontsize=9)
        fig.tight_layout(rect=[0, 0, 1, 0.96])

        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
