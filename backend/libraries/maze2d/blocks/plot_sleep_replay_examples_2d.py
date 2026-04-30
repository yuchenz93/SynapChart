"""Plot example sleep replay events as HSV-coloured 2D spatial maps.

Mirrors plot_replay_examples_2d but operates on decoded_2d_sleep.
The epoch parameter controls which frames to show:
  "pre"  — pre-run sleep only
  "post" — post-run sleep only (default)
  "both" — all epochs, with epoch label in each subplot title
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotSleepReplayExamples2d(BlockBase):
    """Plot sleep replay examples as HSV-coloured 2D maze maps."""

    block_type_id = "plot_sleep_replay_examples_2d"
    display_name  = "Plot Sleep Replay Examples 2D"
    category      = "maze2d / Visualization"
    description   = (
        "Selects the best sleep replay frames (highest spatial range) from pre- "
        "or post-run sleep and plots each as an HSV-coloured 2D spatial map: "
        "hue encodes time of peak decoded probability, saturation encodes peak "
        "probability.  Use the epoch parameter to show 'pre', 'post', or 'both'."
    )

    inputs = [
        PortDefinition("decoded_2d_sleep", "NeuroData[decoded_2d_sleep]",
                       "2D decoded sleep frames from decode_sleep_frames_2d."),
        PortDefinition("place_maps_2d",    "NeuroData[place_maps_2d]",
                       "2D place maps — provides spatial grid and trajectory."),
    ]
    outputs = [
        PortDefinition("sleep_replay_viz", "NeuroData[sleep_replay_viz]",
                       "Summary of shown frames."),
    ]
    parameters = [
        ParameterDefinition("epoch",       "enum:pre,post,both", "post",
                            "Which sleep epoch to show: 'pre', 'post', or 'both'."),
        ParameterDefinition("n_examples",  "int",   8,
                            "Maximum number of replay frames to show per epoch."),
        ParameterDefinition("n_cols",      "int",   4,
                            "Number of columns in the figure grid."),
        ParameterDefinition("max_jump_cm", "float", 50.0,
                            "Only include frames with max position jump ≤ this (cm)."),
        ParameterDefinition("pbclim",      "float", 0.25,
                            "Probability value that maps to full colour saturation."),
        ParameterDefinition("show_on_run", "bool",  True,
                            "Encode figure and display it in the frontend."),
        ParameterDefinition("save_path",   "str",   "",
                            "If non-empty, save figure as PNG to this path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors

        dr: NeuroData = inputs["decoded_2d_sleep"]
        pm: NeuroData = inputs["place_maps_2d"]

        epoch_sel   = str(parameters.get("epoch",       "post")).strip().lower()
        n_examples  = int(parameters.get("n_examples",   8))
        n_cols      = max(1, int(parameters.get("n_cols", 4)))
        jump_thresh = float(parameters.get("max_jump_cm", 50.0))
        pbclim      = float(parameters.get("pbclim",      0.25))
        show        = bool(parameters.get("show_on_run",  True))
        save_path   = str(parameters.get("save_path",    ""))

        all_frames = dr.metadata.get("frames", [])
        valid_ij   = np.asarray(dr.metadata["valid_ij"])
        bcx        = np.asarray(dr.metadata["bin_centers_x"])
        bcy        = np.asarray(dr.metadata["bin_centers_y"])
        n_x        = int(dr.metadata["n_x"])
        n_y        = int(dr.metadata["n_y"])

        pos_2d_cm  = np.asarray(pm.metadata["pos_2d_cm"], dtype=np.float64)
        pos_ts     = np.asarray(pm.metadata["pos_ts"],    dtype=np.float64)

        # ── Select and sort frames ────────────────────────────────────────────
        def _select(frames, n):
            cands = [f for f in frames
                     if float(f.get("max_jump_cm", np.inf)) <= jump_thresh]
            if not cands:
                cands = list(frames)
            cands.sort(key=lambda f: -float(f.get("spatial_range_cm", 0.0)))
            return cands[:n]

        if epoch_sel == "both":
            pre_frames  = _select([f for f in all_frames
                                   if f.get("epoch_label","").lower() == "pre"],  n_examples)
            post_frames = _select([f for f in all_frames
                                   if f.get("epoch_label","").lower() == "post"], n_examples)
            selected = pre_frames + post_frames
        else:
            candidates = [f for f in all_frames
                          if f.get("epoch_label","").lower() == epoch_sel]
            selected = _select(candidates, n_examples)

        if not selected:
            fig, ax = plt.subplots(figsize=(5, 2))
            ax.text(0.5, 0.5, "No replay frames available",
                    ha="center", va="center", transform=ax.transAxes, fontsize=11)
            ax.axis("off")
            viz = save_and_encode(fig, save_path, show)
            return {
                "sleep_replay_viz": NeuroData(
                    data_type="sleep_replay_viz",
                    array=np.array([0.0]),
                    metadata={"n_shown": 0},
                ),
                "_viz": viz,
            }

        n_show = len(selected)
        n_rows = int(np.ceil(n_show / n_cols))
        fig, axes = plt.subplots(n_rows, n_cols,
                                 figsize=(n_cols * 3.2, n_rows * 3.2),
                                 squeeze=False)
        epoch_lbl = epoch_sel.capitalize() if epoch_sel != "both" else "Pre + Post"
        fig.suptitle(
            f"2D Sleep Replay Examples — {epoch_lbl}  (top {n_show} by spatial range)\n"
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
            ep     = str(frame.get("epoch_label", "?"))
            mj     = float(frame.get("max_jump_cm",      np.nan))
            medj   = float(frame.get("med_jump_cm",      np.nan))
            rng    = float(frame.get("spatial_range_cm", np.nan))
            n_spks = int(frame.get("n_spikes",           0))

            post = np.asarray(frame["posterior"], dtype=np.float32)
            n_valid_f, n_t = post.shape

            rgb_img = np.full((n_y, n_x, 3), grey, dtype=np.float32)
            for vi in range(min(n_valid_f, len(valid_ij))):
                xi = int(valid_ij[vi, 0])
                yi = int(valid_ij[vi, 1])
                prob_trace = post[vi, :]
                t_peak = int(np.argmax(prob_trace))
                p_peak = float(prob_trace[t_peak])
                hue = (t_peak / max(n_t - 1, 1)) * (2.0 / 3.0)
                sat = min(1.0, p_peak / max(pbclim, 1e-9))
                rgb_img[yi, xi, :] = mcolors.hsv_to_rgb([hue, sat, 1.0])

            ax.imshow(rgb_img, origin="lower", extent=extent,
                      aspect="equal", interpolation="nearest")

            t_mask = (pos_ts >= t0) & (pos_ts <= t1)
            if t_mask.any():
                ax2x = pos_2d_cm[t_mask, 0]
                ax2y = pos_2d_cm[t_mask, 1]
                n_traj = len(ax2x)
                ax.plot(ax2x, ax2y, "-", color="black", lw=1.2, zorder=5)
                ax.plot(ax2x[0], ax2y[0], "d", ms=6, markerfacecolor="red",
                        markeredgecolor="black", markeredgewidth=0.5, zorder=6)
                mid = n_traj // 2
                ax.plot(ax2x[mid], ax2y[mid], ">", ms=6, markerfacecolor="lime",
                        markeredgecolor="black", markeredgewidth=0.5, zorder=6)
                ax.plot(ax2x[-1], ax2y[-1], "o", ms=6, markerfacecolor="blue",
                        markeredgecolor="black", markeredgewidth=0.5, zorder=6)

            ax.set_title(
                f"[{ep}] F{fidx}  spk={n_spks}\n"
                f"rng={rng:.0f}cm  med={medj:.0f}cm",
                fontsize=7, pad=2,
            )
            ax.axis("off")

        for empty_idx in range(n_show, n_rows * n_cols):
            axes[empty_idx // n_cols][empty_idx % n_cols].set_visible(False)

        plt.tight_layout()
        viz = save_and_encode(fig, save_path, show)

        return {
            "sleep_replay_viz": NeuroData(
                data_type = "sleep_replay_viz",
                array     = np.array([float(f.get("med_jump_cm", np.nan))
                                      for f in selected], dtype=np.float64),
                metadata  = {
                    "n_shown":   n_show,
                    "frame_ids": [int(f["frame_idx"]) for f in selected],
                    "epochs":    [str(f.get("epoch_label","?")) for f in selected],
                },
            ),
            "_viz": viz,
        }
