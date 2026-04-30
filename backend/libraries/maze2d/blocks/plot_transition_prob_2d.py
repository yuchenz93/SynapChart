"""Plot waking-rest decoded transition probability from a reference spatial bin.

Mirrors PlotWRDcdProbTransition from HPCRep_MazeGeometry_OnlineOffline_v2.m.

The transition probability matrix P[i, j] (row-normalised from the directed
transition count matrix T) is reconstructed into 2D maze space.  For the
chosen reference bin (nearest valid bin to the given x,y coordinates), the
row P[ref, :] gives the probability that the decoded position transitions FROM
the reference bin TO every other bin.

Output metadata layout::

    metadata["ref_bin_idx"]   → int   index in valid-bin array
    metadata["ref_x_cm"]      → float actual x-coordinate of chosen bin
    metadata["ref_y_cm"]      → float actual y-coordinate of chosen bin
    metadata["prob_row"]      → np.ndarray (n_valid,) transition probabilities
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotTransitionProb2d(BlockBase):
    """2D heatmap of waking-rest transition probability from a reference bin."""

    block_type_id = "plot_transition_prob_2d"
    display_name  = "Plot Transition Probability 2D"
    category      = "maze2d / Visualization"
    description   = (
        "Shows the transition probability from a chosen reference spatial bin "
        "(nearest valid bin to ref_x_cm, ref_y_cm) to all other valid bins.  "
        "Uses the row P[ref, :] of the row-normalised transition count matrix "
        "from compute_rest_neural_dist.  Mirrors PlotWRDcdProbTransition."
    )

    inputs = [
        PortDefinition("neural_dist_rest", "NeuroData[neural_dist_rest]",
                       "Output of compute_rest_neural_dist (contains P matrix)."),
    ]
    outputs = [
        PortDefinition("transition_prob_viz", "NeuroData[transition_prob_viz]",
                       "Reference bin info and transition probability row."),
    ]
    parameters = [
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

        nd: NeuroData = inputs["neural_dist_rest"]

        ref_x      = float(parameters.get("ref_x_cm",    0.0))
        ref_y      = float(parameters.get("ref_y_cm",   -10.0))
        vmax       = float(parameters.get("vmax",         0.02))
        cmap       = str(parameters.get("cmap",          "rainbow"))
        show       = bool(parameters.get("show_on_run",   True))
        save_path  = str(parameters.get("save_path",     ""))

        # ── Unpack ────────────────────────────────────────────────────────────
        P        = np.asarray(nd.metadata["transition_prob"])    # (n_valid, n_valid)
        valid_ij = np.asarray(nd.metadata["valid_ij"])           # (n_valid, 2) [xi, yi]
        bcx      = np.asarray(nd.metadata["bin_centers_x"])
        bcy      = np.asarray(nd.metadata["bin_centers_y"])
        n_x      = int(nd.metadata["n_x"])
        n_y      = int(nd.metadata["n_y"])
        n_valid  = int(nd.metadata["n_valid"])

        valid_x  = bcx[valid_ij[:, 0]]   # (n_valid,) cm
        valid_y  = bcy[valid_ij[:, 1]]   # (n_valid,) cm

        # ── Find nearest valid bin to reference coordinates ───────────────────
        dists   = np.sqrt((valid_x - ref_x) ** 2 + (valid_y - ref_y) ** 2)
        ref_idx = int(np.argmin(dists))
        actual_x = float(valid_x[ref_idx])
        actual_y = float(valid_y[ref_idx])

        prob_row = P[ref_idx, :]   # (n_valid,) probability from ref → others

        # ── Reconstruct 2D map ────────────────────────────────────────────────
        prob_map = np.full(n_x * n_y, np.nan)
        flat_idx = valid_ij[:, 0] * n_y + valid_ij[:, 1]
        prob_map[flat_idx] = prob_row
        prob_map = prob_map.reshape(n_x, n_y)   # (n_x, n_y)

        # ── Plot ──────────────────────────────────────────────────────────────
        dx = float(bcx[1] - bcx[0]) if len(bcx) > 1 else 1.0
        dy = float(bcy[1] - bcy[0]) if len(bcy) > 1 else 1.0
        extent = [float(bcx[0]) - dx/2, float(bcx[-1]) + dx/2,
                  float(bcy[0]) - dy/2, float(bcy[-1]) + dy/2]

        fig, ax = plt.subplots(figsize=(6, 5))

        im = ax.imshow(
            prob_map.T,         # transpose: x→col, y→row, display as (n_y, n_x)
            origin="lower",
            extent=extent,
            aspect="equal",
            interpolation="nearest",
            cmap=cmap,
            vmin=0.0,
            vmax=vmax,
        )

        # Mark the reference bin
        ax.plot(actual_x, actual_y, "k^",
                markersize=8, markeredgewidth=1.5, zorder=5,
                label=f"Ref ({actual_x:.1f}, {actual_y:.1f}) cm")

        cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cb.set_label("Transition Probability")
        ax.set_xlabel("X (cm)")
        ax.set_ylabel("Y (cm)")
        ax.set_title(
            f"Transition Probability from ({actual_x:.1f}, {actual_y:.1f}) cm\n"
            f"total out-transitions: {int(prob_row.sum() > 0)} bins reached",
            fontsize=9,
        )
        ax.legend(fontsize=8, loc="upper right")
        plt.tight_layout()

        viz = save_and_encode(fig, save_path, show)

        return {
            "transition_prob_viz": NeuroData(
                data_type = "transition_prob_viz",
                array     = prob_row.astype(np.float64),
                metadata  = {
                    "ref_bin_idx": ref_idx,
                    "ref_x_cm":   actual_x,
                    "ref_y_cm":   actual_y,
                    "prob_row":   prob_row.astype(np.float64),
                },
            ),
            "_viz": viz,
        }
