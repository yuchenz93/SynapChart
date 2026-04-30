"""Plot theta phase precession summary.

For each cell × field: scatter of (normalised position, theta phase).
A second axes shows the distribution of r values across selected cells.
"""


from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotPhasePrecessionSummary(BlockBase):
    """Plot phase-vs-position scatters and r-value distribution."""

    block_type_id = "plot_phase_precession_summary"
    display_name  = "Plot Phase Precession Summary"
    category      = "Visualization"
    description   = (
        "Shows per-cell phase-vs-position scatters and a histogram of r values "
        "across selected cells. Pyramidal-cell r values are highlighted."
    )

    inputs = [
        PortDefinition("phase_precession", "NeuroData[phase_precession]",
                       "Phase precession stats from compute_phase_precession."),
    ]
    outputs: list[PortDefinition] = []
    parameters = [
        ParameterDefinition("cell_filter", "enum:all,pyramidal,interneuron", "pyramidal",
                            "Which cells to include in the r distribution."),
        ParameterDefinition("max_scatter_cells", "int", 20,
                            "Max individual scatter plots shown (0 = distribution only)."),
        ParameterDefinition("close_all",    "bool", True,
                            "Call plt.close('all') before plotting."),
        ParameterDefinition("show_on_run",  "bool", True,   "Show in viz panel."),
        ParameterDefinition("save_path",    "str",  "",     "PNG save path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        pp: NeuroData = inputs["phase_precession"]

        cell_filt   = str(parameters.get("cell_filter",       "pyramidal"))
        max_scatter = int(parameters.get("max_scatter_cells", 20))
        close_all   = bool(parameters.get("close_all",        True))
        show        = bool(parameters.get("show_on_run",      True))
        save_path   = str(parameters.get("save_path",         ""))

        if close_all:
            plt.close("all")

        results   = pp.metadata.get("results", {})
        cell_ids  = pp.metadata.get("cell_ids", [])
        pyr_set   = set(str(c) for c in pp.metadata.get("pyr_ids", []))
        int_set   = set(str(c) for c in pp.metadata.get("int_ids", []))

        # Filter
        if cell_filt == "pyramidal":
            sel_ids = [c for c in cell_ids if str(c) in pyr_set]
        elif cell_filt == "interneuron":
            sel_ids = [c for c in cell_ids if str(c) in int_set]
        else:
            sel_ids = list(cell_ids)

        # Collect r values and scatter data
        r_values: list[float] = []
        scatter_data: list[tuple] = []  # (positions, phases, r, cell_id, field_i)

        for cid in sel_ids:
            for fi, fld in enumerate(results.get(str(cid), [])):
                r = fld.get("r", np.nan)
                if np.isnan(r):
                    continue
                r_values.append(r)
                if len(scatter_data) < max_scatter and fld.get("positions"):
                    scatter_data.append((
                        np.array(fld["positions"]),
                        np.array(fld["phases"]),
                        r,
                        str(cid),
                        fi,
                    ))

        n_scatter = min(len(scatter_data), max_scatter)
        n_scatter = n_scatter if max_scatter > 0 else 0

        if n_scatter == 0:
            # Distribution-only figure
            fig, ax = plt.subplots(figsize=(6, 4))
            if r_values:
                ax.hist(r_values, bins=25, range=(-1, 1), color="#3b82f6",
                        edgecolor="white", linewidth=0.5)
                ax.axvline(np.median(r_values), color="#ef4444", linewidth=1.5,
                           label=f"median = {np.median(r_values):.3f}")
                ax.axvline(0, color="#9ca3af", linewidth=0.8, linestyle="--", alpha=0.6)
                ax.legend(fontsize=11)
            ax.set_xlabel("Pearson r (position vs phase)", fontsize=13)
            ax.set_ylabel("# fields", fontsize=13)
            ax.set_title(
                f"Phase precession — {cell_filt} ({len(r_values)} fields)", fontsize=14
            )
            ax.tick_params(labelsize=11)
            ax.spines[["top", "right"]].set_visible(False)
            fig.tight_layout()
        else:
            # Grid of scatters + histogram
            n_cols = min(n_scatter, 5)
            n_rows = int(np.ceil(n_scatter / n_cols)) + 1   # +1 for histogram row

            fig = plt.figure(figsize=(n_cols * 2.6, n_rows * 2.4))
            gs  = gridspec.GridSpec(n_rows, n_cols, figure=fig, hspace=0.55, wspace=0.45)

            for idx, (pos_norm, phases, r_val, cid, fi) in enumerate(scatter_data[:n_scatter]):
                row = idx // n_cols
                col = idx % n_cols
                ax  = fig.add_subplot(gs[row, col])
                ax.scatter(pos_norm, np.rad2deg(phases), s=4, alpha=0.55,
                           color="#3b82f6" if str(cid) in pyr_set else "#f97316",
                           linewidths=0)
                ax.set_title(f"c{cid} f{fi}\nr={r_val:.2f}", fontsize=8, pad=2)
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 360)
                ax.set_yticks([0, 90, 180, 270, 360])
                ax.tick_params(labelsize=7)
                ax.spines[["top", "right"]].set_visible(False)

            # Histogram spanning full bottom row
            ax_hist = fig.add_subplot(gs[-1, :])
            if r_values:
                ax_hist.hist(r_values, bins=25, range=(-1, 1), color="#3b82f6",
                             edgecolor="white", linewidth=0.5)
                ax_hist.axvline(np.median(r_values), color="#ef4444", linewidth=1.5,
                                label=f"median = {np.median(r_values):.3f}")
                ax_hist.axvline(0, color="#9ca3af", linewidth=0.8,
                                linestyle="--", alpha=0.6)
                ax_hist.legend(fontsize=10)
            ax_hist.set_xlabel("Pearson r (position vs phase)", fontsize=12)
            ax_hist.set_ylabel("# fields", fontsize=12)
            ax_hist.set_title(
                f"r distribution ({cell_filt}, {len(r_values)} fields)", fontsize=12
            )
            ax_hist.tick_params(labelsize=10)
            ax_hist.spines[["top", "right"]].set_visible(False)
            fig.suptitle("Theta Phase Precession", fontsize=14, y=1.01)

        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
