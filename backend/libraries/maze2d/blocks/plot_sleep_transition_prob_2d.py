"""Plot waking-sleep decoded transition probability from a reference spatial bin.

The epoch parameter selects which transition matrix to visualise:
  "pre"  — pre-run sleep transition probability
  "post" — post-run sleep transition probability (default)
  "both" — side-by-side panels for pre and post

Uses P[ref, :] from the row-normalised transition matrix stored in
neural_dist_sleep (computed by compute_sleep_neural_dist).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


def _panel(ax, P, valid_ij, bcx, bcy, n_x, n_y, ref_x, ref_y,
           vmax, cmap, title):
    """Draw one transition-probability heatmap on ax."""
    valid_x = bcx[valid_ij[:, 0]]
    valid_y = bcy[valid_ij[:, 1]]
    dists   = np.sqrt((valid_x - ref_x) ** 2 + (valid_y - ref_y) ** 2)
    ref_idx = int(np.argmin(dists))
    actual_x = float(valid_x[ref_idx])
    actual_y = float(valid_y[ref_idx])

    prob_row = P[ref_idx, :]
    prob_map = np.full(n_x * n_y, np.nan)
    flat_idx = valid_ij[:, 0] * n_y + valid_ij[:, 1]
    prob_map[flat_idx] = prob_row
    prob_map = prob_map.reshape(n_x, n_y)

    dx = float(bcx[1] - bcx[0]) if len(bcx) > 1 else 1.0
    dy = float(bcy[1] - bcy[0]) if len(bcy) > 1 else 1.0
    extent = [float(bcx[0]) - dx/2, float(bcx[-1]) + dx/2,
              float(bcy[0]) - dy/2, float(bcy[-1]) + dy/2]

    im = ax.imshow(prob_map.T, origin="lower", extent=extent,
                   aspect="equal", interpolation="nearest",
                   cmap=cmap, vmin=0.0, vmax=vmax)
    ax.plot(actual_x, actual_y, "k^", markersize=8, markeredgewidth=1.5, zorder=5,
            label=f"Ref ({actual_x:.1f}, {actual_y:.1f}) cm")
    ax.set_xlabel("X (cm)")
    ax.set_ylabel("Y (cm)")
    ax.set_title(f"{title}\n({actual_x:.1f}, {actual_y:.1f}) cm", fontsize=9)
    ax.legend(fontsize=7, loc="upper right")
    return im, ref_idx


class PlotSleepTransitionProb2d(BlockBase):
    """2D heatmap of sleep transition probability from a reference bin."""

    block_type_id = "plot_sleep_transition_prob_2d"
    display_name  = "Plot Sleep Transition Probability 2D"
    category      = "maze2d / Visualization"
    description   = (
        "Shows the transition probability from a chosen reference spatial bin "
        "to all other valid bins for pre-run and/or post-run sleep.  "
        "Use the epoch parameter to show 'pre', 'post', or 'both' (side-by-side)."
    )

    inputs = [
        PortDefinition("neural_dist_sleep", "NeuroData[neural_dist_sleep]",
                       "Output of compute_sleep_neural_dist."),
    ]
    outputs = [
        PortDefinition("sleep_transition_viz", "NeuroData[sleep_transition_viz]",
                       "Reference bin info."),
    ]
    parameters = [
        ParameterDefinition("epoch",       "enum:pre,post,both", "both",
                            "Which epoch to show: 'pre', 'post', or 'both'."),
        ParameterDefinition("ref_x_cm",    "float", 0.0,
                            "X-coordinate (cm) of the reference spatial bin."),
        ParameterDefinition("ref_y_cm",    "float", -10.0,
                            "Y-coordinate (cm) of the reference spatial bin."),
        ParameterDefinition("vmax",        "float", 0.02,
                            "Colormap upper limit for transition probability."),
        ParameterDefinition("cmap",        "str",   "rainbow",
                            "Matplotlib colormap name."),
        ParameterDefinition("show_on_run", "bool",  True,
                            "Encode figure and display it in the frontend."),
        ParameterDefinition("save_path",   "str",   "",
                            "If non-empty, save figure as PNG to this path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import matplotlib.pyplot as plt

        nd: NeuroData = inputs["neural_dist_sleep"]

        epoch_sel = str(parameters.get("epoch",      "both")).strip().lower()
        ref_x     = float(parameters.get("ref_x_cm",  0.0))
        ref_y     = float(parameters.get("ref_y_cm", -10.0))
        vmax      = float(parameters.get("vmax",       0.02))
        cmap      = str(parameters.get("cmap",         "rainbow"))
        show      = bool(parameters.get("show_on_run", True))
        save_path = str(parameters.get("save_path",    ""))

        valid_ij = np.asarray(nd.metadata["valid_ij"])
        bcx      = np.asarray(nd.metadata["bin_centers_x"])
        bcy      = np.asarray(nd.metadata["bin_centers_y"])
        n_x      = int(nd.metadata["n_x"])
        n_y      = int(nd.metadata["n_y"])
        P_pre    = np.asarray(nd.metadata["transition_prob_pre"])
        P_post   = np.asarray(nd.metadata["transition_prob_post"])

        if epoch_sel == "both":
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            im, ri_pre  = _panel(axes[0], P_pre,  valid_ij, bcx, bcy, n_x, n_y,
                                 ref_x, ref_y, vmax, cmap, "Pre-sleep Transition Prob")
            im, ri_post = _panel(axes[1], P_post, valid_ij, bcx, bcy, n_x, n_y,
                                 ref_x, ref_y, vmax, cmap, "Post-sleep Transition Prob")
            for ax in axes:
                fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04).set_label(
                    "Transition Probability")
        else:
            P = P_pre if epoch_sel == "pre" else P_post
            label = "Pre-sleep" if epoch_sel == "pre" else "Post-sleep"
            fig, ax = plt.subplots(figsize=(6, 5))
            im, _ = _panel(ax, P, valid_ij, bcx, bcy, n_x, n_y,
                           ref_x, ref_y, vmax, cmap, f"{label} Transition Prob")
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04).set_label(
                "Transition Probability")

        plt.tight_layout()
        viz = save_and_encode(fig, save_path, show)

        return {
            "sleep_transition_viz": NeuroData(
                data_type = "sleep_transition_viz",
                array     = np.array([0.0]),
                metadata  = {"epoch": epoch_sel},
            ),
            "_viz": viz,
        }
