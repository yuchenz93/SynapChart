"""Plot a grid of example 2D firing-rate place maps.

Shows up to n_examples cells (selected by peak firing rate) as side-by-side
heatmaps on the 2D spatial grid.  Useful for verifying that the place maps
cover only the intended track region and that bad-stamp / epoch filtering
worked correctly.

Output metadata layout::

    metadata["n_shown"]      → int   number of cells plotted
    metadata["cell_ids"]     → list  cell IDs shown (in plot order)
    metadata["peak_rates"]   → list  peak firing rate per shown cell (Hz)
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotPlaceMaps2d(BlockBase):
    """Grid of example 2D firing-rate place maps."""

    block_type_id = "plot_place_maps_2d"
    display_name  = "Plot 2D Place Maps"
    category      = "maze2d / Visualization"
    description   = (
        "Plots a grid of 2D firing-rate maps for the cells with the highest "
        "peak firing rate.  Use this to verify maze coverage and spot "
        "artefacts from bad tracking stamps or out-of-epoch samples."
    )

    inputs = [
        PortDefinition("place_maps_2d", "NeuroData[place_maps_2d]",
                       "2D place maps from compute_place_maps_2d."),
    ]
    outputs = [
        PortDefinition("place_maps_viz", "NeuroData[place_maps_viz]",
                       "Pass-through summary with n_shown and peak rate info."),
    ]
    parameters = [
        ParameterDefinition("n_examples",  "int",   25,
                            "Number of cells to show (highest peak rate first)."),
        ParameterDefinition("n_cols",      "int",   5,
                            "Number of columns in the grid."),
        ParameterDefinition("cmap",        "str",   "hot_r",
                            "Colormap for rate maps."),
        ParameterDefinition("show_valid",  "bool",  True,
                            "Overlay the valid-bin boundary as a grey contour."),
        ParameterDefinition("show_on_run", "bool",  True,
                            "Encode figure and display it in the frontend."),
        ParameterDefinition("save_path",   "str",   "",
                            "If non-empty, save figure as PNG to this path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker

        pm: NeuroData = inputs["place_maps_2d"]

        n_examples  = int(parameters.get("n_examples",  25))
        n_cols      = int(parameters.get("n_cols",       5))
        cmap        = str(parameters.get("cmap",        "hot_r"))
        show_valid  = bool(parameters.get("show_valid",  True))
        show        = bool(parameters.get("show_on_run", True))
        save_path   = str(parameters.get("save_path",   ""))

        rate_maps  = np.asarray(pm.metadata["maps"],        dtype=np.float64)  # (n_cells, n_x, n_y)
        valid_mask = np.asarray(pm.metadata["valid_mask"],  dtype=bool)         # (n_x, n_y)
        bcx        = np.asarray(pm.metadata["bin_centers_x"])
        bcy        = np.asarray(pm.metadata["bin_centers_y"])
        cell_ids   = list(pm.metadata["cell_ids"])
        n_cells    = rate_maps.shape[0]

        # ── Select cells by peak firing rate ──────────────────────────────────
        peak_rates = np.nanmax(rate_maps.reshape(n_cells, -1), axis=1)  # (n_cells,)
        order      = np.argsort(peak_rates)[::-1]                        # descending
        n_show     = min(n_examples, n_cells)
        sel        = order[:n_show]

        shown_ids   = [cell_ids[i] for i in sel]
        shown_peaks = [float(peak_rates[i]) for i in sel]

        # ── Layout ────────────────────────────────────────────────────────────
        n_rows = int(np.ceil(n_show / n_cols))
        fig, axes = plt.subplots(
            n_rows, n_cols,
            figsize=(n_cols * 2.8, n_rows * 2.6),
            squeeze=False,
        )
        fig.suptitle(
            f"2D place maps — top {n_show} cells by peak rate  "
            f"(grid {len(bcx)}×{len(bcy)}, {len(bcx)*4:.0f}×{len(bcy)*4:.0f} cm)",
            fontsize=11,
        )

        # Spatial extent for imshow
        dx = float(bcx[1] - bcx[0]) if len(bcx) > 1 else 4.0
        dy = float(bcy[1] - bcy[0]) if len(bcy) > 1 else 4.0
        extent = [
            float(bcx[0])  - dx / 2,
            float(bcx[-1]) + dx / 2,
            float(bcy[0])  - dy / 2,
            float(bcy[-1]) + dy / 2,
        ]

        for plot_idx, cell_idx in enumerate(sel):
            row = plot_idx // n_cols
            col = plot_idx  % n_cols
            ax  = axes[row][col]

            rmap = rate_maps[cell_idx].T.copy()   # (n_y, n_x) for imshow
            rmap[~valid_mask.T] = np.nan          # grey-out invalid bins

            vmax = float(np.nanmax(rmap)) if np.any(np.isfinite(rmap)) else 1.0
            im = ax.imshow(
                rmap,
                origin="lower",
                extent=extent,
                aspect="equal",
                cmap=cmap,
                vmin=0.0,
                vmax=vmax,
                interpolation="nearest",
            )

            if show_valid:
                # Draw valid-bin boundary as thin grey contour
                ax.contour(
                    valid_mask.T.astype(float),
                    levels=[0.5],
                    colors=["#888888"],
                    linewidths=[0.5],
                    extent=extent,
                    origin="lower",
                )

            cbar = plt.colorbar(im, ax=ax, pad=0.02, fraction=0.046)
            cbar.ax.tick_params(labelsize=6)
            cbar.set_label("Hz", fontsize=6)

            ax.set_title(
                f"cell {shown_ids[plot_idx]}  {shown_peaks[plot_idx]:.1f} Hz",
                fontsize=7,
            )
            ax.set_xlabel("X (cm)", fontsize=6)
            ax.set_ylabel("Y (cm)", fontsize=6)
            ax.tick_params(labelsize=6)

        # Hide unused axes
        for plot_idx in range(n_show, n_rows * n_cols):
            axes[plot_idx // n_cols][plot_idx % n_cols].set_visible(False)

        plt.tight_layout()
        viz = save_and_encode(fig, save_path, show)

        return {
            "place_maps_viz": NeuroData(
                data_type = "place_maps_viz",
                array     = np.array(shown_peaks),
                metadata  = {
                    "n_shown":    n_show,
                    "cell_ids":   shown_ids,
                    "peak_rates": shown_peaks,
                },
            ),
            "_viz": viz,
        }
