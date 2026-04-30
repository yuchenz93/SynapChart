"""Plot behavior-scale decoding: actual vs decoded position during running laps.

Intended as a verification step — run Bayesian decoder at 200 ms bins during
laps and compare the MAP decoded position to the animal's actual trajectory.
"""


from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotBehaviorDecoding(BlockBase):
    """Plot actual vs MAP-decoded position during running laps."""

    block_type_id = "plot_behavior_decoding"
    display_name  = "Plot Behavior Decoding"
    category      = "Visualization"
    description   = (
        "Plots actual position (line) against MAP-decoded position (dots) for "
        "each running lap.  Computes and reports median absolute decoding error."
    )

    inputs = [
        PortDefinition("decoded",  "NeuroData[decoded]",
                       "Posterior matrix (n_pos_bins × n_time_bins) from Bayesian decoder."),
        PortDefinition("position", "NeuroData[position]",
                       "Linearised 1-D position with timestamps (cm)."),
        PortDefinition("laps",     "NeuroData[laps]",
                       "Lap table from detect_run_laps."),
        PortDefinition("tuning_curves", "NeuroData[tuning_curves_population]",
                       "Population tuning curves — provides position bin centres.",
                       required=False),
    ]
    outputs: list[PortDefinition] = []
    parameters = [
        ParameterDefinition("max_laps_shown", "int", 6,
                            "Number of individual laps to show side-by-side (0 = all)."),
        ParameterDefinition("close_all",  "bool", True,
                            "Call plt.close('all') before plotting."),
        ParameterDefinition("show_on_run", "bool", True, "Emit figure to viz panel."),
        ParameterDefinition("save_path",   "str",  "",   "PNG save path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        decoded: NeuroData = inputs["decoded"]
        pos:     NeuroData = inputs["position"]
        laps:    NeuroData = inputs["laps"]
        tc                 = inputs.get("tuning_curves")

        max_show  = int(parameters.get("max_laps_shown", 6))
        close_all = bool(parameters.get("close_all",     True))
        show      = bool(parameters.get("show_on_run",   True))
        save_path = str(parameters.get("save_path",      ""))

        if close_all:
            plt.close("all")

        posterior = decoded.array               # (n_pos_bins, n_time_bins)
        dec_ts    = decoded.timestamps
        n_pos     = posterior.shape[0]

        # Position bin centres
        if tc is not None and tc.timestamps is not None:
            bin_centers = np.asarray(tc.timestamps)
        else:
            p_min = float(decoded.metadata.get("pos_min", 0.0))
            p_max = float(decoded.metadata.get("pos_max", 160.0))
            bin_centers = np.linspace(p_min, p_max, n_pos)

        if dec_ts is None:
            bin_sec = float(decoded.metadata.get("bin_size_sec", 0.2))
            dec_ts  = np.arange(posterior.shape[1]) * bin_sec

        # MAP decoded position
        map_pos = bin_centers[np.argmax(posterior, axis=0)]   # (n_time_bins,)

        pos_1d = pos.array.flatten()
        pos_ts = pos.timestamps
        if pos_ts is None:
            pos_sr = pos.sampling_rate or 39.0
            pos_ts = np.arange(len(pos_1d)) / pos_sr

        lap_list = laps.metadata.get("laps", [])

        # Error across all laps
        all_errors: list[float] = []
        for lap in lap_list:
            dec_mask = (dec_ts >= lap["t_start"]) & (dec_ts <= lap["t_end"])
            if dec_mask.sum() == 0:
                continue
            actual = np.interp(dec_ts[dec_mask], pos_ts, pos_1d)
            all_errors.extend(np.abs(actual - map_pos[dec_mask]).tolist())

        median_err = float(np.median(all_errors)) if all_errors else float("nan")

        # ── Plot individual laps ──────────────────────────────────────────────
        show_laps = lap_list if max_show == 0 else lap_list[:max_show]
        n_show    = len(show_laps)

        if n_show == 0:
            fig, ax = plt.subplots(figsize=(6, 3))
            ax.text(0.5, 0.5, "No laps found in decoded time range.",
                    ha="center", va="center", transform=ax.transAxes)
            fig.suptitle("Behavior-scale decoding", fontsize=10)
            viz = save_and_encode(fig, save_path, show)
            return {"_viz": viz} if viz else {}

        n_cols = min(n_show, 3)
        n_rows = int(np.ceil(n_show / n_cols))
        fig, axes = plt.subplots(n_rows, n_cols,
                                  figsize=(n_cols * 4, n_rows * 3),
                                  squeeze=False)

        col_dir = {1: "#3b82f6", 2: "#f97316"}

        for li, lap in enumerate(show_laps):
            row, col = divmod(li, n_cols)
            ax = axes[row][col]

            dec_mask = (dec_ts >= lap["t_start"]) & (dec_ts <= lap["t_end"])
            pos_mask = (pos_ts >= lap["t_start"]) & (pos_ts <= lap["t_end"])

            t0 = lap["t_start"]
            ax.plot(pos_ts[pos_mask] - t0, pos_1d[pos_mask],
                    color="#374151", linewidth=1.5, label="Actual", zorder=3)

            if dec_mask.sum() > 0:
                lap_map = map_pos[dec_mask]
                actual  = np.interp(dec_ts[dec_mask], pos_ts, pos_1d)
                lap_err = float(np.median(np.abs(actual - lap_map)))
                ax.scatter(dec_ts[dec_mask] - t0, lap_map,
                           s=14, c=col_dir.get(lap["direction"], "#6b7280"),
                           alpha=0.85, label="Decoded", zorder=4, linewidths=0)
                ax.set_title(
                    f"Lap {li+1} · dir{lap['direction']} · err={lap_err:.1f} cm",
                    fontsize=11,
                )
            else:
                ax.set_title(f"Lap {li+1} · dir{lap['direction']} · no data", fontsize=11)

            ax.set_xlabel("Time in lap (s)", fontsize=11)
            ax.set_ylabel("Position (cm)",   fontsize=11)
            ax.tick_params(labelsize=10)
            if li == 0:
                ax.legend(fontsize=10, loc="upper left")

        # Hide unused subplots
        for li in range(n_show, n_rows * n_cols):
            row, col = divmod(li, n_cols)
            axes[row][col].set_visible(False)

        fig.suptitle(
            f"Behavior-scale decoding  (median error = {median_err:.1f} cm, "
            f"n = {len(lap_list)} laps total)",
            fontsize=13,
        )
        fig.tight_layout()

        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
