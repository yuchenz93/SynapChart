"""Plot theta phase precession summary for every state."""


from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotPhasePrecession1d(BlockBase):
    """Phase-vs-position scatters and r-distribution per state."""

    block_type_id = "plot_phase_precession_1d"
    display_name  = "Plot Phase Precession 1D"
    category      = "maze1d / Visualization"
    description   = (
        "For each selected state: per-cell phase-vs-position scatter plots and a "
        "histogram of Pearson r values across pyramidal cells.  "
        "Phase is in [0°, 360°]; negative r indicates precession."
    )

    inputs = [
        PortDefinition("phase_precession", "NeuroData[phase_precession_1d]",
                       "Per-state precession stats from compute_phase_precession_1d."),
    ]
    outputs: list = []
    parameters = [
        ParameterDefinition("state_keys",       "str",  "",
                            "Comma-separated state names.  Empty = all."),
        ParameterDefinition("cell_filter",       "enum:all,pyramidal,interneuron", "pyramidal",
                            "Which cells to include in the r distribution."),
        ParameterDefinition("max_scatter_cells", "int",  12,
                            "Max individual scatter plots per state (0 = histogram only)."),
        ParameterDefinition("close_all",         "bool", True,  "Close existing figures."),
        ParameterDefinition("show_on_run",        "bool", True,  "Show in viz panel."),
        ParameterDefinition("save_path",          "str",  "",    "PNG save path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        pp: NeuroData = inputs["phase_precession"]

        keys_str    = str(parameters.get("state_keys",        "")).strip()
        cell_filt   = str(parameters.get("cell_filter",        "pyramidal"))
        max_scatter = int(parameters.get("max_scatter_cells",  12))
        close_all   = bool(parameters.get("close_all",         True))
        show        = bool(parameters.get("show_on_run",        True))
        save_path   = str(parameters.get("save_path",           ""))

        if close_all:
            plt.close("all")

        results_by_state = pp.metadata.get("results_by_state", {})
        all_keys         = pp.metadata.get("state_keys", list(results_by_state.keys()))
        selected_keys    = [k.strip() for k in keys_str.split(",") if k.strip()] \
                           if keys_str else all_keys
        selected_keys    = [k for k in selected_keys if k in results_by_state]

        pyr_set = set(str(c) for c in pp.metadata.get("pyr_ids", []))
        int_set = set(str(c) for c in pp.metadata.get("int_ids", []))

        n_states = len(selected_keys)
        if n_states == 0:
            fig, ax = plt.subplots(figsize=(5, 3))
            ax.text(0.5, 0.5, "No states.", ha="center", va="center",
                    transform=ax.transAxes)
            viz = save_and_encode(fig, save_path, show)
            return {"_viz": viz} if viz else {}

        fig = plt.figure(figsize=(max(8, max_scatter * 2.2), n_states * 4.5))
        outer_gs = gridspec.GridSpec(n_states, 1, figure=fig, hspace=0.6)

        for si, sname in enumerate(selected_keys):
            results = results_by_state[sname]
            cell_ids = list(results.keys())

            if cell_filt == "pyramidal":
                sel_ids = [c for c in cell_ids if c in pyr_set]
            elif cell_filt == "interneuron":
                sel_ids = [c for c in cell_ids if c in int_set]
            else:
                sel_ids = list(cell_ids)

            r_values: list[float]             = []
            scatter_data: list[tuple]          = []

            for cid in sel_ids:
                for fi, fld in enumerate(results.get(cid, [])):
                    r = fld.get("r", np.nan)
                    if np.isnan(r):
                        continue
                    r_values.append(r)
                    if len(scatter_data) < max_scatter and fld.get("positions"):
                        scatter_data.append((
                            np.array(fld["positions"]),
                            np.array(fld["phases"]),
                            r, cid, fi,
                        ))

            n_scatter = min(len(scatter_data), max_scatter) if max_scatter > 0 else 0
            n_cols    = max(n_scatter + 1, 2)   # +1 for histogram

            inner_gs = gridspec.GridSpecFromSubplotSpec(
                1, n_cols, subplot_spec=outer_gs[si], wspace=0.4,
            )

            for idx, (pos_n, phases, r_v, cid, fi) in enumerate(scatter_data[:n_scatter]):
                ax = fig.add_subplot(inner_gs[idx])
                c  = "#3b82f6" if cid in pyr_set else "#f97316"
                ax.scatter(pos_n, np.rad2deg(phases), s=5, alpha=0.55,
                           color=c, linewidths=0)
                ax.set_title(f"c{cid} f{fi}\nr={r_v:.2f}", fontsize=8, pad=2)
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 360)
                ax.set_yticks([0, 180, 360])
                ax.tick_params(labelsize=7)
                ax.spines[["top", "right"]].set_visible(False)

            ax_hist = fig.add_subplot(inner_gs[-1])
            if r_values:
                ax_hist.hist(r_values, bins=20, range=(-1, 1),
                             color="#3b82f6", edgecolor="white", linewidth=0.5)
                ax_hist.axvline(np.median(r_values), color="#ef4444", linewidth=1.5,
                                label=f"median={np.median(r_values):.2f}")
                ax_hist.axvline(0, color="#9ca3af", linewidth=0.8, linestyle="--",
                                alpha=0.6)
                ax_hist.legend(fontsize=9)
            ax_hist.set_xlabel("Pearson r", fontsize=11)
            ax_hist.set_ylabel("# fields",  fontsize=11)
            ax_hist.set_title(f"{sname}\n({len(r_values)} fields)", fontsize=11)
            ax_hist.tick_params(labelsize=10)
            ax_hist.spines[["top", "right"]].set_visible(False)

        fig.suptitle("Theta Phase Precession", fontsize=14, y=1.01)
        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
