"""Plot per-state averaged theta sequence heatmaps."""


from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotThetaSequences1d(BlockBase):
    """Heatmaps of averaged theta sequences — one panel per selected state."""

    block_type_id = "plot_theta_sequences_1d"
    display_name  = "Plot Theta Sequences 1D"
    category      = "maze1d / Visualization"
    description   = (
        "Shows the averaged decoded-posterior theta sequence for each selected "
        "state.  x-axis: time relative to cycle centre / theta trough (ms); "
        "y-axis: position relative to the animal (cm)."
    )

    inputs = [
        PortDefinition("theta_sequences", "NeuroData[theta_sequence_1d]",
                       "Per-state sequences from compute_theta_sequences_1d."),
    ]
    outputs: list = []
    parameters = [
        ParameterDefinition("state_keys",   "str",  "",
                            "Comma-separated state names to display.  Empty = all."),
        ParameterDefinition("theta_freq_hz","float", 8.0,
                            "Theta frequency — used for ±½-cycle marker lines."),
        ParameterDefinition("ylim_cm",      "float", 40.0,
                            "Half-range of y-axis in cm (0 = auto)."),
        ParameterDefinition("colormap",     "str",   "hot",   "Matplotlib colormap."),
        ParameterDefinition("close_all",    "bool",  True,    "Close existing figures."),
        ParameterDefinition("show_on_run",  "bool",  True,    "Show in viz panel."),
        ParameterDefinition("save_path",    "str",   "",      "PNG save path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        ts: NeuroData = inputs["theta_sequences"]

        keys_str   = str(parameters.get("state_keys",   "")).strip()
        theta_hz   = float(parameters.get("theta_freq_hz", 8.0))
        ylim_cm    = float(parameters.get("ylim_cm",        40.0))
        cmap       = str(parameters.get("colormap",     "hot"))
        close_all  = bool(parameters.get("close_all",    True))
        show       = bool(parameters.get("show_on_run",  True))
        save_path  = str(parameters.get("save_path",     ""))

        if close_all:
            plt.close("all")

        sequences_all  = ts.metadata.get("sequences", {})
        all_keys       = ts.metadata.get("state_keys", list(sequences_all.keys()))
        selected_keys  = [k.strip() for k in keys_str.split(",") if k.strip()] \
                         if keys_str else all_keys
        selected_keys  = [k for k in selected_keys if k in sequences_all]

        if not selected_keys:
            fig, ax = plt.subplots(figsize=(5, 3))
            ax.text(0.5, 0.5, "No states selected.", ha="center", va="center",
                    transform=ax.transAxes)
            viz = save_and_encode(fig, save_path, show)
            return {"_viz": viz} if viz else {}

        lag_positions  = np.array(ts.metadata.get("lag_positions", []))
        bin_width_cm   = float(ts.metadata.get("bin_width_cm", 1.0))
        half_ms        = float(ts.metadata.get("half_window_ms", 180.0))
        n_cycles_dict  = ts.metadata.get("n_cycles_by_state", {})

        # Timestamps in seconds → milliseconds
        if ts.timestamps is not None:
            t_ms = np.asarray(ts.timestamps) * 1000.0
        else:
            n_t  = list(sequences_all.values())[0].shape[0]
            t_ms = np.linspace(-half_ms, half_ms, n_t)

        lag_cm = lag_positions * bin_width_cm

        n_states = len(selected_keys)
        fig, axes = plt.subplots(1, n_states,
                                  figsize=(n_states * 7, 5),
                                  squeeze=False)

        half_cycle_ms = 500.0 / theta_hz
        extent        = [t_ms[0], t_ms[-1], lag_cm[0] if len(lag_cm) else -half_ms,
                         lag_cm[-1] if len(lag_cm) else half_ms]

        for col, sname in enumerate(selected_keys):
            matrix   = sequences_all[sname]   # (n_time, n_lag)
            n_cycles = n_cycles_dict.get(sname, 0)
            ax       = axes[0][col]

            im = ax.imshow(
                matrix.T,
                aspect="auto", origin="lower",
                extent=extent, cmap=cmap, interpolation="bilinear",
            )

            ax.axvline(0, color="cyan", linewidth=1.2, linestyle="--", alpha=0.9,
                       label="trough")
            ax.axhline(0, color="white", linewidth=0.8, linestyle=":", alpha=0.7,
                       label="animal pos")
            ax.axvline(-half_cycle_ms, color="cyan", linewidth=0.6, linestyle=":",
                       alpha=0.4)
            ax.axvline( half_cycle_ms, color="cyan", linewidth=0.6, linestyle=":",
                       alpha=0.4)

            ax.set_xlim(t_ms[0], t_ms[-1])
            if ylim_cm > 0:
                ax.set_ylim(-ylim_cm, ylim_cm)

            ax.set_xlabel("Time rel. to trough (ms)", fontsize=13)
            ax.set_ylabel("Position rel. to animal (cm)\n[+ = ahead]", fontsize=12)
            ax.set_title(f"{sname}\n(n = {n_cycles} cycles)", fontsize=13)
            ax.tick_params(labelsize=11)
            if col == 0:
                ax.legend(loc="upper right", fontsize=9)

            cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
            cbar.set_label("Avg. decoded prob.", fontsize=10)
            cbar.ax.tick_params(labelsize=9)

        fig.suptitle("Theta Sequences", fontsize=14, y=1.01)
        fig.tight_layout()
        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
