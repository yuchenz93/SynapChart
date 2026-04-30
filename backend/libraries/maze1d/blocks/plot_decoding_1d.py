"""Plot actual vs MAP-decoded position for each state — state-aware."""


from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotDecoding1d(BlockBase):
    """Plot actual vs decoded position for every state's laps."""

    block_type_id = "plot_decoding_1d"
    display_name  = "Plot Decoding 1D"
    category      = "maze1d / Visualization"
    description   = (
        "Shows actual position (line) vs MAP decoded position (dots) for laps "
        "in each selected state.  Reports median absolute error per state."
    )

    inputs = [
        PortDefinition("decoded",  "NeuroData[decoded_1d]",
                       "Per-state posteriors from decode_position_1d (behavioral bins, ~0.2 s)."),
        PortDefinition("position", "NeuroData[position]",
                       "Linearised 1-D position with timestamps."),
        PortDefinition("states",   "NeuroData[states]",
                       "Named states — provides lap intervals per state."),
    ]
    outputs: list = []
    parameters = [
        ParameterDefinition("state_keys",    "str",  "",
                            "Comma-separated state names to display.  Empty = all."),
        ParameterDefinition("max_laps_shown","int",  4,
                            "Laps to show per state (0 = all)."),
        ParameterDefinition("close_all",     "bool", True,  "Close existing figures."),
        ParameterDefinition("show_on_run",   "bool", True,  "Show in viz panel."),
        ParameterDefinition("save_path",     "str",  "",    "PNG save path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        decoded:   NeuroData = inputs["decoded"]
        pos:       NeuroData = inputs["position"]
        states_nd: NeuroData = inputs["states"]

        keys_str  = str(parameters.get("state_keys",    "")).strip()
        max_show  = int(parameters.get("max_laps_shown", 4))
        close_all = bool(parameters.get("close_all",     True))
        show      = bool(parameters.get("show_on_run",   True))
        save_path = str(parameters.get("save_path",      ""))

        if close_all:
            plt.close("all")

        posteriors_all = decoded.metadata.get("posteriors", {})
        all_keys       = decoded.metadata.get("state_keys", list(posteriors_all.keys()))
        selected_keys  = [k.strip() for k in keys_str.split(",") if k.strip()] \
                         if keys_str else all_keys
        selected_keys  = [k for k in selected_keys if k in posteriors_all]

        dec_times   = decoded.timestamps
        bin_centers = np.array(decoded.metadata.get("bin_centers", []))

        pos_1d = pos.array.flatten()
        pos_ts = pos.timestamps
        if pos_ts is None:
            pos_ts = np.arange(len(pos_1d)) / (pos.sampling_rate or 39.0)

        states_dict = states_nd.metadata.get("states", {})

        n_states = len(selected_keys)
        if n_states == 0 or dec_times is None or len(bin_centers) == 0:
            fig, ax = plt.subplots(figsize=(6, 3))
            ax.text(0.5, 0.5, "No data to plot.", ha="center", va="center",
                    transform=ax.transAxes)
            viz = save_and_encode(fig, save_path, show)
            return {"_viz": viz} if viz else {}

        col_dir = {1: "#3b82f6", 2: "#f97316", None: "#6b7280"}
        n_cols  = min(max_show if max_show > 0 else 6, 4)
        n_rows  = n_states

        fig, axes = plt.subplots(n_rows, n_cols,
                                  figsize=(n_cols * 3.5, n_rows * 3.0),
                                  squeeze=False)

        for row, sname in enumerate(selected_keys):
            posterior = posteriors_all[sname]     # (n_pos, n_time)
            map_pos   = bin_centers[np.argmax(posterior, axis=0)]
            direction = states_dict.get(sname, {}).get("direction")
            color     = col_dir.get(direction, "#6b7280")
            intervals = states_dict.get(sname, {}).get("intervals", [])

            all_errors: list[float] = []
            laps_shown = 0

            for col_i, (t0, t1) in enumerate(intervals):
                dec_mask = (dec_times >= t0) & (dec_times <= t1)
                pos_mask = (pos_ts >= t0) & (pos_ts <= t1)
                if dec_mask.sum() == 0:
                    continue

                actual = np.interp(dec_ts := dec_times[dec_mask], pos_ts, pos_1d)
                errs   = np.abs(actual - map_pos[dec_mask])
                all_errors.extend(errs.tolist())

                if laps_shown < n_cols:
                    ax = axes[row][laps_shown]
                    lap_err = float(np.median(errs))
                    ax.plot(pos_ts[pos_mask] - t0, pos_1d[pos_mask],
                            color="#374151", linewidth=1.5, label="Actual", zorder=3)
                    ax.scatter(dec_ts - t0, map_pos[dec_mask],
                               s=12, c=color, alpha=0.8, zorder=4, linewidths=0,
                               label="Decoded")
                    ax.set_title(f"Lap {laps_shown+1}  err={lap_err:.1f} cm",
                                 fontsize=10)
                    ax.set_xlabel("Time (s)", fontsize=10)
                    ax.set_ylabel("Position (cm)", fontsize=10)
                    ax.tick_params(labelsize=9)
                    if laps_shown == 0:
                        ax.legend(fontsize=9, loc="upper left")
                    laps_shown += 1
                    if max_show > 0 and laps_shown >= max_show:
                        break

            # Hide unused subplots in this row
            for ci in range(laps_shown, n_cols):
                axes[row][ci].set_visible(False)

            med_err = float(np.median(all_errors)) if all_errors else float("nan")
            axes[row][0].set_ylabel(f"{sname}\nPosition (cm)", fontsize=10)
            axes[row][max(0, min(n_cols - 1, laps_shown - 1))].annotate(
                f"median err = {med_err:.1f} cm",
                xy=(1, 1), xycoords="axes fraction",
                ha="right", va="top", fontsize=8, color="#6b7280",
            )

        fig.suptitle("Behavioral decoding — actual vs decoded position",
                     fontsize=13, y=1.01)
        fig.tight_layout()
        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
