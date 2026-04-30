"""Plot linearised position vs time, colour-coded by lap direction."""


from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotLaps(BlockBase):
    """Plot position vs time with direction-coloured lap segments."""

    block_type_id = "plot_laps"
    display_name  = "Plot Run Laps"
    category      = "Visualization"
    description   = (
        "Shows linearised position (cm) vs time. Running laps are overlaid in "
        "blue (direction 1, descending) and orange (direction 2, ascending)."
    )

    inputs = [
        PortDefinition("position", "NeuroData[position]",
                       "Linearised 1-D position with timestamps (cm)."),
        PortDefinition("laps",     "NeuroData[laps]",
                       "Lap table from detect_run_laps."),
    ]
    outputs: list[PortDefinition] = []
    parameters = [
        ParameterDefinition("t_window_s", "float", 120.0,
                            "Seconds of recording to display (0 = full session)."),
        ParameterDefinition("close_all",  "bool", True,
                            "Call plt.close('all') before plotting."),
        ParameterDefinition("show_on_run", "bool", True,  "Emit figure to viz panel."),
        ParameterDefinition("save_path",   "str",  "",    "PNG save path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        pos:  NeuroData = inputs["position"]
        laps: NeuroData = inputs["laps"]

        t_win     = float(parameters.get("t_window_s",  120.0))
        close_all = bool(parameters.get("close_all",    True))
        show      = bool(parameters.get("show_on_run",  True))
        save_path = str(parameters.get("save_path",     ""))

        if close_all:
            plt.close("all")

        pos_1d = pos.array.flatten()
        pos_ts = pos.timestamps
        if pos_ts is None:
            pos_sr = pos.sampling_rate or 39.0
            pos_ts = np.arange(len(pos_1d)) / pos_sr

        # Restrict display window
        t_start_plot = float(pos_ts[0])
        t_end_plot   = (t_start_plot + t_win) if t_win > 0 else float(pos_ts[-1])
        t_end_plot   = min(t_end_plot, float(pos_ts[-1]))

        mask     = (pos_ts >= t_start_plot) & (pos_ts <= t_end_plot)
        plot_ts  = pos_ts[mask]
        plot_pos = pos_1d[mask]

        fig, ax = plt.subplots(figsize=(14, 4))

        # Full trajectory in light grey
        ax.plot(plot_ts, plot_pos, color="#d1d5db", linewidth=0.5, zorder=1)

        # Direction colours
        col = {1: "#3b82f6", 2: "#f97316"}

        lap_list = laps.metadata.get("laps", [])
        for lap in lap_list:
            if lap["t_start"] > t_end_plot:
                break
            t_seg_end = min(lap["t_end"], t_end_plot)
            seg = (pos_ts >= lap["t_start"]) & (pos_ts <= t_seg_end)
            if seg.sum() < 2:
                continue
            ax.plot(pos_ts[seg], pos_1d[seg],
                    color=col[lap["direction"]], linewidth=1.2, zorder=2)

        ax.set_xlabel("Time (s)", fontsize=11)
        ax.set_ylabel("Linearised position (cm)", fontsize=11)

        n1 = laps.metadata.get("n_laps_dir1", 0)
        n2 = laps.metadata.get("n_laps_dir2", 0)
        ax.set_title(
            f"Running laps — {n1} descending (dir 1) · {n2} ascending (dir 2)",
            fontsize=11,
        )

        legend_handles = [
            Line2D([0], [0], color="#3b82f6", lw=2,
                   label=f"Dir 1 — descending  (n = {n1})"),
            Line2D([0], [0], color="#f97316", lw=2,
                   label=f"Dir 2 — ascending   (n = {n2})"),
        ]
        ax.legend(handles=legend_handles, loc="upper right", fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()

        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
