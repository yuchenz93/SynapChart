"""Plot the discretized maze nodes and directed edges around a reference point.

Mirrors PlotZoominNodesWeights from HPCRep_MazeGeometry_OnlineOffline_v2.m.

Edge style encodes the transition-probability-based edge weight W = (-log P)^gamma:
  - Low weight  (strong connection): thin, dark line
  - High weight (weak connection):   thick, light line

Only edges with both endpoints inside the view region and with weight in
[weight_min, weight_max] are shown.  Up to max_edges edges are sampled
(sorted by weight descending so weaker/lighter edges are drawn first and
stronger/darker ones on top).

Output metadata layout::

    metadata["ref_bin_idx"]  → int   index of reference bin in valid array
    metadata["ref_x_cm"]     → float
    metadata["ref_y_cm"]     → float
    metadata["n_edges_shown"]→ int
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotNodesEdges2d(BlockBase):
    """Maze graph nodes and directed edges coloured by transition weight."""

    block_type_id = "plot_nodes_edges_2d"
    display_name  = "Plot Nodes & Edges 2D"
    category      = "maze2d / Visualization"
    description   = (
        "Plots the discretized maze spatial bins (nodes) and directed "
        "transition-weight edges in a zoom region around a reference point.  "
        "Edge darkness/thickness encodes connection strength.  "
        "Mirrors PlotZoominNodesWeights."
    )

    inputs = [
        PortDefinition("neural_dist_rest", "NeuroData[neural_dist_rest]",
                       "Output of compute_rest_neural_dist (contains W matrix)."),
    ]
    outputs = [
        PortDefinition("nodes_edges_viz", "NeuroData[nodes_edges_viz]",
                       "Summary (ref bin, n_edges shown)."),
    ]
    parameters = [
        ParameterDefinition("ref_x_cm",      "float",  0.0,
                            "X-coordinate (cm) of the reference point / view centre."),
        ParameterDefinition("ref_y_cm",      "float", -10.0,
                            "Y-coordinate (cm) of the reference point / view centre."),
        ParameterDefinition("zoom_radius_cm","float",  50.0,
                            "Half-width of the view window around the reference point (cm). "
                            "Set to a large value to show the entire maze."),
        ParameterDefinition("weight_min",    "float",  0.02,
                            "Minimum edge weight to show (edges below are too strong / "
                            "would clutter the figure)."),
        ParameterDefinition("weight_max",    "float",  0.5,
                            "Maximum edge weight to show (edges above are near-zero "
                            "transition probability)."),
        ParameterDefinition("max_edges",     "int",    800,
                            "Maximum number of edges to draw (random sample if exceeded)."),
        ParameterDefinition("random_seed",   "int",    42,
                            "Random seed for edge sampling when max_edges is exceeded."),
        ParameterDefinition("show_on_run",   "bool",   True,
                            "Encode figure and display it in the frontend."),
        ParameterDefinition("save_path",     "str",    "",
                            "If non-empty, save figure as PNG to this path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import matplotlib.pyplot as plt

        nd: NeuroData = inputs["neural_dist_rest"]

        ref_x       = float(parameters.get("ref_x_cm",       0.0))
        ref_y       = float(parameters.get("ref_y_cm",      -10.0))
        zoom_r      = float(parameters.get("zoom_radius_cm", 50.0))
        w_min       = float(parameters.get("weight_min",      0.02))
        w_max       = float(parameters.get("weight_max",      0.5))
        max_edges   = int(parameters.get("max_edges",         800))
        seed        = int(parameters.get("random_seed",        42))
        show        = bool(parameters.get("show_on_run",       True))
        save_path   = str(parameters.get("save_path",         ""))

        # ── Unpack ────────────────────────────────────────────────────────────
        W        = np.asarray(nd.metadata["edge_weights"])      # (n_valid, n_valid)
        valid_ij = np.asarray(nd.metadata["valid_ij"])          # (n_valid, 2) [xi, yi]
        bcx      = np.asarray(nd.metadata["bin_centers_x"])
        bcy      = np.asarray(nd.metadata["bin_centers_y"])
        n_valid  = int(nd.metadata["n_valid"])

        valid_x  = bcx[valid_ij[:, 0]]   # (n_valid,) cm
        valid_y  = bcy[valid_ij[:, 1]]   # (n_valid,) cm

        # ── View limits ───────────────────────────────────────────────────────
        xlim = (ref_x - zoom_r, ref_x + zoom_r)
        ylim = (ref_y - zoom_r, ref_y + zoom_r)

        in_view = ((valid_x >= xlim[0]) & (valid_x <= xlim[1]) &
                   (valid_y >= ylim[0]) & (valid_y <= ylim[1]))

        # ── Find reference bin ────────────────────────────────────────────────
        dists   = np.sqrt((valid_x - ref_x) ** 2 + (valid_y - ref_y) ** 2)
        ref_idx = int(np.argmin(dists))

        # ── Collect edges within view and weight range ────────────────────────
        # Only consider entries where both endpoints are in-view
        in_view_idx = np.where(in_view)[0]
        src_arr, dst_arr, w_arr = [], [], []

        if len(in_view_idx) > 0:
            sub_W = W[np.ix_(in_view_idx, in_view_idx)]  # (n_in, n_in)
            ii, jj = np.where((sub_W >= w_min) & (sub_W <= w_max) &
                              (sub_W < 1e5))   # exclude large_weight sentinel
            w_vals = sub_W[ii, jj]
            # Map back to global valid indices
            src_arr = in_view_idx[ii]
            dst_arr = in_view_idx[jj]
            w_arr   = w_vals

        n_edges_total = len(w_arr)

        # Sample if too many
        if n_edges_total > max_edges:
            rng  = np.random.default_rng(seed)
            keep = rng.choice(n_edges_total, size=max_edges, replace=False)
            src_arr = src_arr[keep]
            dst_arr = dst_arr[keep]
            w_arr   = w_arr[keep]

        # Sort by weight descending so lighter/weaker edges are drawn first
        # and stronger/darker edges appear on top
        if len(w_arr) > 0:
            order   = np.argsort(w_arr)[::-1]
            src_arr = src_arr[order]
            dst_arr = dst_arr[order]
            w_arr   = w_arr[order]

        n_edges_shown = len(w_arr)

        # ── Figure ────────────────────────────────────────────────────────────
        fig, ax = plt.subplots(figsize=(6, 6))

        # Draw edges
        if n_edges_shown > 0:
            # Normalise weights to [0, 1] within [w_min, w_max]
            wn = (np.clip(w_arr, w_min, w_max) - w_min) / (w_max - w_min + 1e-9)

            lw_min, lw_max   = 0.15, 1.0
            g_dark, g_light  = 0.20, 0.92

            lw_vals = lw_max - (lw_max - lw_min) * wn   # low weight → thick
            g_vals  = g_dark + (g_light - g_dark) * wn  # low weight → dark

            xs_src = valid_x[src_arr]
            ys_src = valid_y[src_arr]
            xs_dst = valid_x[dst_arr]
            ys_dst = valid_y[dst_arr]

            for k in range(n_edges_shown):
                ax.plot([xs_src[k], xs_dst[k]],
                        [ys_src[k], ys_dst[k]],
                        "-", color=[g_vals[k]] * 3,
                        linewidth=lw_vals[k],
                        solid_capstyle="round",
                        zorder=1)

        # Draw all in-view nodes
        ax.plot(valid_x[in_view], valid_y[in_view],
                "ko", markersize=1.75, linewidth=0.8, zorder=2)

        # Mark reference bin
        ax.plot(valid_x[ref_idx], valid_y[ref_idx], "r^",
                markersize=9, markeredgecolor="black",
                markeredgewidth=0.8, zorder=5,
                label=f"Ref ({valid_x[ref_idx]:.1f}, {valid_y[ref_idx]:.1f}) cm")

        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        ax.set_aspect("equal")
        ax.set_xlabel("X (cm)")
        ax.set_ylabel("Y (cm)")
        ax.set_title(
            f"Maze nodes & edges  (weight [{w_min:.2f}, {w_max:.2f}])\n"
            f"{n_edges_shown} edges shown  |  "
            f"darker/thinner = stronger connection",
            fontsize=9,
        )
        ax.legend(fontsize=8, loc="upper right")
        plt.tight_layout()

        viz = save_and_encode(fig, save_path, show)

        return {
            "nodes_edges_viz": NeuroData(
                data_type = "nodes_edges_viz",
                array     = np.array([n_edges_shown], dtype=np.float64),
                metadata  = {
                    "ref_bin_idx":   ref_idx,
                    "ref_x_cm":      float(valid_x[ref_idx]),
                    "ref_y_cm":      float(valid_y[ref_idx]),
                    "n_edges_shown": n_edges_shown,
                },
            ),
            "_viz": viz,
        }
