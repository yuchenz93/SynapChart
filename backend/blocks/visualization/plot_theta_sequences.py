"""Visualise the averaged theta sequence look-ahead/look-behind matrix.

Axes use physical units:
  x  — time relative to the cycle centre (theta trough) in milliseconds
       (default ±180 ms window spans ~3 theta cycles at 8 Hz)
  y  — position relative to the animal in cm
       (converted from position bins using bin_width_cm from metadata)
"""


from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotThetaSequences(BlockBase):
    """Plot the averaged theta sequence (look-ahead / look-behind) heatmap."""

    block_type_id = "plot_theta_sequences"
    display_name  = "Plot Theta Sequences"
    category      = "Visualization"
    description   = (
        "Heatmap of averaged decoded posteriors aligned to the animal's position "
        "across theta cycles.  x-axis: time relative to cycle centre / theta trough "
        "(ms, default ±180 ms = ~3 cycles).  y-axis: position relative to animal (cm)."
    )

    inputs = [
        PortDefinition("theta_sequences", "NeuroData[theta_sequence]",
                       "Averaged theta sequence matrix from compute_theta_sequences."),
    ]
    outputs: list[PortDefinition] = []
    parameters = [
        ParameterDefinition("theta_freq_hz", "float", 8.0,
                            "Assumed theta frequency (Hz). Used to draw optional "
                            "cycle-boundary markers at ±1/2 cycle from centre."),
        ParameterDefinition("ylim_cm",     "float", 40.0,
                            "Half-range of y-axis in cm (animal ± ylim_cm).  0 = auto."),
        ParameterDefinition("colormap",    "str",  "hot",
                            "Matplotlib colormap name."),
        ParameterDefinition("show_on_run", "bool", True,  "Show in viz panel."),
        ParameterDefinition("save_path",   "str",  "",    "PNG save path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        ts: NeuroData = inputs["theta_sequences"]

        theta_hz  = float(parameters.get("theta_freq_hz", 8.0))
        ylim_cm   = float(parameters.get("ylim_cm",       40.0))
        cmap      = str(parameters.get("colormap",    "hot"))
        show      = bool(parameters.get("show_on_run", True))
        save_path = str(parameters.get("save_path",    ""))

        matrix   = ts.array                     # (n_time_per_cycle, n_pos_lags)
        lag_bins = np.array(ts.metadata.get("lag_positions",
                                             np.arange(matrix.shape[1])))
        n_cycles = int(ts.metadata.get("n_cycles", 0))
        bw_cm    = float(ts.metadata.get("bin_width_cm", 1.0))
        hw_ms    = float(ts.metadata.get("half_window_ms", 180.0))

        # timestamps are in seconds relative to cycle centre (from compute_theta_sequences)
        if ts.timestamps is not None:
            t_ms = np.asarray(ts.timestamps) * 1000.0
        else:
            # Legacy fallback: timestamps were normalised [0,1]; convert via theta_hz
            t_norm = np.linspace(0, 1, matrix.shape[0])
            cycle_ms = 1000.0 / theta_hz
            t_ms = (t_norm - 0.5) * cycle_ms

        # Position lags (bins) → cm relative to animal
        lag_cm = lag_bins * bw_cm

        # ── Plot ──────────────────────────────────────────────────────────────
        fig, ax = plt.subplots(figsize=(8, 5))

        extent = [t_ms[0], t_ms[-1], lag_cm[0], lag_cm[-1]]
        im = ax.imshow(
            matrix.T,
            aspect="auto",
            origin="lower",
            extent=extent,
            cmap=cmap,
            interpolation="bilinear",
        )

        # Axis limits
        ax.set_xlim(t_ms[0], t_ms[-1])
        if ylim_cm > 0:
            ax.set_ylim(-ylim_cm, ylim_cm)

        # Reference lines: cycle centre and animal position
        ax.axvline(0, color="cyan", linewidth=1.2, linestyle="--",
                   label="trough (current pos)", alpha=0.9)
        ax.axhline(0, color="white", linewidth=0.8, linestyle=":",
                   alpha=0.7, label="animal position")

        # Optional: mark ±1/2 cycle boundaries relative to centre
        half_cycle_ms = 500.0 / theta_hz
        ax.axvline(-half_cycle_ms, color="cyan", linewidth=0.6, linestyle=":",
                   alpha=0.4)
        ax.axvline( half_cycle_ms, color="cyan", linewidth=0.6, linestyle=":",
                   alpha=0.4)

        ax.set_xlabel("Time relative to theta trough (ms)", fontsize=14)
        ax.set_ylabel("Position relative to animal (cm)",   fontsize=14)
        ax.set_title(
            f"Theta sequences   (n = {n_cycles} cycles)",
            fontsize=15,
        )
        ax.tick_params(labelsize=12)
        ax.legend(loc="upper right", fontsize=10)

        cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
        cbar.set_label("Avg. decoded probability", fontsize=11)
        cbar.ax.tick_params(labelsize=10)

        fig.tight_layout()
        viz = save_and_encode(fig, save_path, show)
        return {"_viz": viz} if viz else {}
