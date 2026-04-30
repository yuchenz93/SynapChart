"""Plot example waking-rest replay events as HSV-coloured 2D spatial maps.

Each selected replay frame is shown in one subplot on a multi-column grid.
The visualisation mirrors gui_Bdecode_8arm_plot2DSummary:

  * For every valid 2D spatial bin, the decoded posterior probability at
    that bin is used directly from the 2D posterior (n_valid × n_tbins).
  * **Hue**        = time of peak probability within the frame
                     (red = start, green = middle, blue = end).
  * **Saturation** = peak probability normalised by pbclim
                     (white = low probability, vivid = high).
  * **Value**      = 1  (constant brightness).
  * **Grey**       = unvisited bins (outside valid mask).

Animal trajectory during the frame is overlaid:
  black line, red diamond (start), green right-pointing triangle (middle),
  blue circle (end).

Frame selection:
  1. Optional filter: max_jump_cm <= jump_thresh.
  2. Ranked by med_jump_cm ascending (most coherent/sequential first).

Output metadata layout::

    metadata["n_shown"]      → int
    metadata["frame_ids"]    → list[int]
    metadata["med_jumps"]    → list[float]  cm
    metadata["max_jumps"]    → list[float]  cm
    metadata["n_spikes"]     → list[int]
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotReplayExamples2d(BlockBase):
    """Plot waking-rest replay examples as HSV-coloured 2D maze maps."""

    block_type_id = "plot_replay_examples_2d"
    display_name  = "Plot 2D Replay Examples"
    category      = "maze2d / Visualization"
    description   = (
        "Selects the best waking-rest replay frames (lowest median jump, within "
        "max_jump_cm limit) and plots each as an HSV-coloured 2D spatial map: "
        "hue encodes time of peak decoded probability, saturation encodes peak "
        "probability.  Animal trajectory during the frame is overlaid.  "
        "Multi-column layout.  Uses true 2D decoded posteriors from "
        "decode_rest_frames_2d."
    )

    inputs = [
        PortDefinition("decoded_2d_rest", "NeuroData[decoded_2d_rest]",
                       "2D decoded rest frames from decode_rest_frames_2d."),
        PortDefinition("place_maps_2d",   "NeuroData[place_maps_2d]",
                       "2D place maps — provides occupancy grid and trajectory."),
    ]
    outputs = [
        PortDefinition("replay_examples_viz", "NeuroData[replay_examples_viz]",
                       "Summary of shown frames (n_shown, jump sizes, n_spikes)."),
    ]
    parameters = [
        ParameterDefinition("n_examples",  "int",   12,
                            "Maximum number of replay frames to show."),
        ParameterDefinition("n_cols",      "int",   4,
                            "Number of columns in the figure grid."),
        ParameterDefinition("max_jump_cm", "float", 50.0,
                            "Only include frames with max position jump ≤ this (cm)."),
        ParameterDefinition("pbclim",      "float", 0.25,
                            "Probability value that maps to full colour saturation.  "
                            "Lower = more vivid colours for weaker replays."),
        ParameterDefinition("show_on_run", "bool",  True,
                            "Encode figure and display it in the frontend."),
        ParameterDefinition("save_path",   "str",   "",
                            "If non-empty, save figure as PNG to this path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors

        dr: NeuroData = inputs["decoded_2d_rest"]
        pm: NeuroData = inputs["place_maps_2d"]

        n_examples  = int(parameters.get("n_examples",   12))
        n_cols      = max(1, int(parameters.get("n_cols",  4)))
        jump_thresh = float(parameters.get("max_jump_cm", 50.0))
        pbclim      = float(parameters.get("pbclim",      0.25))
        show        = bool(parameters.get("show_on_run",  True))
        save_path   = str(parameters.get("save_path",    ""))

        # ── Unpack decoded_2d_rest ────────────────────────────────────────────
        frames    = dr.metadata["frames"]            # list[dict]
        valid_ij  = np.asarray(dr.metadata["valid_ij"])   # (n_valid, 2) [xi, yi]
        bcx       = np.asarray(dr.metadata["bin_centers_x"])
        bcy       = np.asarray(dr.metadata["bin_centers_y"])
        n_x       = int(dr.metadata["n_x"])
        n_y       = int(dr.metadata["n_y"])

        # ── Unpack place_maps_2d (for trajectory overlay) ────────────────────
        pos_2d_cm = np.asarray(pm.metadata["pos_2d_cm"], dtype=np.float64)  # (N, 2)
        pos_ts    = np.asarray(pm.metadata["pos_ts"],    dtype=np.float64)  # (N,)

        # ── Select frames ─────────────────────────────────────────────────────
        candidates = [f for f in frames
                      if float(f.get("max_jump_cm", np.inf)) <= jump_thresh]

        if not candidates:
            candidates = list(frames)   # relax filter

        # Sort by spatial range descending (most track coverage first)
        candidates.sort(key=lambda f: -float(f.get("spatial_range_cm", 0.0)))
        selected = candidates[:n_examples]

        if not selected:
            fig, ax = plt.subplots(figsize=(5, 2))
            ax.text(0.5, 0.5, "No replay frames available",
                    ha="center", va="center", transform=ax.transAxes, fontsize=11)
            ax.axis("off")
            viz = save_and_encode(fig, save_path, show)
            return {
                "replay_examples_viz": NeuroData(
                    data_type = "replay_examples_viz",
                    array     = np.array([0.0]),
                    metadata  = {"n_shown": 0, "frame_ids": [],
                                 "med_jumps": [], "max_jumps": [], "n_spikes": []},
                ),
                "_viz": viz,
            }

        n_show = len(selected)

        # ── Figure layout ─────────────────────────────────────────────────────
        n_rows = int(np.ceil(n_show / n_cols))
        fig, axes = plt.subplots(
            n_rows, n_cols,
            figsize=(n_cols * 3.2, n_rows * 3.2),
            squeeze=False,
        )
        fig.suptitle(
            f"2D Replay Examples — top {n_show} by spatial range"
            f"  (max_jump≤{jump_thresh:.0f}cm)\n"
            "Hue: time in frame (red→blue)   Sat: decode probability",
            fontsize=9,
        )

        dx = float(bcx[1] - bcx[0]) if len(bcx) > 1 else 1.0
        dy = float(bcy[1] - bcy[0]) if len(bcy) > 1 else 1.0
        extent = [float(bcx[0]) - dx/2, float(bcx[-1]) + dx/2,
                  float(bcy[0]) - dy/2, float(bcy[-1]) + dy/2]

        grey = 0.82

        for plot_idx, frame in enumerate(selected):
            row = plot_idx // n_cols
            col = plot_idx  % n_cols
            ax  = axes[row][col]

            t0     = float(frame["t_start"])
            t1     = float(frame["t_end"])
            fidx   = int(frame["frame_idx"])
            mj     = float(frame.get("max_jump_cm",      np.nan))
            medj   = float(frame.get("med_jump_cm",      np.nan))
            rng    = float(frame.get("spatial_range_cm", np.nan))
            n_spks = int(frame.get("n_spikes",           0))

            post = np.asarray(frame["posterior"], dtype=np.float32)  # (n_valid, n_tbins)
            n_valid_f, n_t = post.shape

            # ── Build HSV image (n_y, n_x, 3) ─────────────────────────────
            rgb_img = np.full((n_y, n_x, 3), grey, dtype=np.float32)

            for vi in range(min(n_valid_f, len(valid_ij))):
                xi = int(valid_ij[vi, 0])   # x index → column
                yi = int(valid_ij[vi, 1])   # y index → row

                prob_trace = post[vi, :]            # (n_t,)
                t_peak     = int(np.argmax(prob_trace))
                p_peak     = float(prob_trace[t_peak])

                hue = (t_peak / max(n_t - 1, 1)) * (2.0 / 3.0)
                sat = min(1.0, p_peak / max(pbclim, 1e-9))
                rgb_img[yi, xi, :] = mcolors.hsv_to_rgb([hue, sat, 1.0])

            ax.imshow(rgb_img, origin="lower", extent=extent,
                      aspect="equal", interpolation="nearest")

            # ── Animal trajectory overlay ──────────────────────────────────
            t_mask = (pos_ts >= t0) & (pos_ts <= t1)
            if t_mask.any():
                ax2x = pos_2d_cm[t_mask, 0]
                ax2y = pos_2d_cm[t_mask, 1]
                n_traj = len(ax2x)
                ax.plot(ax2x, ax2y, "-", color="black", lw=1.2, zorder=5)
                ax.plot(ax2x[0], ax2y[0], "d",
                        ms=6, markerfacecolor="red",
                        markeredgecolor="black", markeredgewidth=0.5, zorder=6)
                mid = n_traj // 2
                ax.plot(ax2x[mid], ax2y[mid], ">",
                        ms=6, markerfacecolor="lime",
                        markeredgecolor="black", markeredgewidth=0.5, zorder=6)
                ax.plot(ax2x[-1], ax2y[-1], "o",
                        ms=6, markerfacecolor="blue",
                        markeredgecolor="black", markeredgewidth=0.5, zorder=6)

            ax.set_title(
                f"F{fidx}  spk={n_spks}\n"
                f"rng={rng:.0f}cm  med={medj:.0f}cm",
                fontsize=7, pad=2,
            )
            ax.axis("off")

        # Hide unused subplot slots
        for empty_idx in range(n_show, n_rows * n_cols):
            axes[empty_idx // n_cols][empty_idx % n_cols].set_visible(False)

        plt.tight_layout()
        viz = save_and_encode(fig, save_path, show)

        return {
            "replay_examples_viz": NeuroData(
                data_type = "replay_examples_viz",
                array     = np.array([float(f.get("med_jump_cm", np.nan))
                                      for f in selected], dtype=np.float64),
                metadata  = {
                    "n_shown":   n_show,
                    "frame_ids": [int(f["frame_idx"]) for f in selected],
                    "med_jumps": [float(f.get("med_jump_cm", np.nan)) for f in selected],
                    "max_jumps": [float(f.get("max_jump_cm", np.nan)) for f in selected],
                    "n_spikes":  [int(f.get("n_spikes",      0))      for f in selected],
                },
            ),
            "_viz": viz,
        }
