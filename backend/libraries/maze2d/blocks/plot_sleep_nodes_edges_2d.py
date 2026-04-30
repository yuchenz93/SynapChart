"""Plot discretized maze nodes and directed edges for sleep neural distance.

The epoch parameter selects which edge-weight matrix to visualise:
  "pre"  — pre-run sleep
  "post" — post-run sleep (default)
  "both" — side-by-side panels for pre and post

Edge style encodes connection strength exactly as in plot_nodes_edges_2d:
  darker/thinner = lower weight = stronger connection.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


def _draw_panel(ax, W, valid_ij, bcx, bcy,
                ref_x, ref_y, zoom_r,
                w_min, w_max, max_edges, seed):
    """Draw nodes + edges on ax.  Returns n_edges_shown, ref_idx."""
    valid_x = bcx[valid_ij[:, 0]]
    valid_y = bcy[valid_ij[:, 1]]

    xlim = (ref_x - zoom_r, ref_x + zoom_r)
    ylim = (ref_y - zoom_r, ref_y + zoom_r)

    in_view = ((valid_x >= xlim[0]) & (valid_x <= xlim[1]) &
               (valid_y >= ylim[0]) & (valid_y <= ylim[1]))
    in_view_idx = np.where(in_view)[0]

    dists   = np.sqrt((valid_x - ref_x) ** 2 + (valid_y - ref_y) ** 2)
    ref_idx = int(np.argmin(dists))

    src_arr, dst_arr, w_arr = [], [], []
    if len(in_view_idx) > 0:
        sub_W = W[np.ix_(in_view_idx, in_view_idx)]
        ii, jj = np.where((sub_W >= w_min) & (sub_W <= w_max) & (sub_W < 1e5))
        w_vals  = sub_W[ii, jj]
        src_arr = in_view_idx[ii]
        dst_arr = in_view_idx[jj]
        w_arr   = w_vals

    n_total = len(w_arr)
    if n_total > max_edges:
        rng  = np.random.default_rng(seed)
        keep = rng.choice(n_total, size=max_edges, replace=False)
        src_arr = src_arr[keep]
        dst_arr = dst_arr[keep]
        w_arr   = w_arr[keep]

    if len(w_arr) > 0:
        order   = np.argsort(w_arr)[::-1]
        src_arr = src_arr[order]
        dst_arr = dst_arr[order]
        w_arr   = w_arr[order]
        wn = (np.clip(w_arr, w_min, w_max) - w_min) / (w_max - w_min + 1e-9)
        lw_min, lw_max  = 0.15, 1.0
        g_dark, g_light = 0.20, 0.92
        lw_vals = lw_max - (lw_max - lw_min) * wn
        g_vals  = g_dark + (g_light - g_dark) * wn
        xs_src = valid_x[src_arr]; ys_src = valid_y[src_arr]
        xs_dst = valid_x[dst_arr]; ys_dst = valid_y[dst_arr]
        for k in range(len(w_arr)):
            ax.plot([xs_src[k], xs_dst[k]], [ys_src[k], ys_dst[k]],
                    "-", color=[g_vals[k]] * 3, linewidth=lw_vals[k],
                    solid_capstyle="round", zorder=1)

    ax.plot(valid_x[in_view], valid_y[in_view],
            "ko", markersize=1.75, linewidth=0.8, zorder=2)
    ax.plot(valid_x[ref_idx], valid_y[ref_idx], "r^",
            markersize=9, markeredgecolor="black", markeredgewidth=0.8, zorder=5,
            label=f"Ref ({valid_x[ref_idx]:.1f}, {valid_y[ref_idx]:.1f}) cm")
    ax.set_xlim(xlim); ax.set_ylim(ylim)
    ax.set_aspect("equal")
    ax.set_xlabel("X (cm)"); ax.set_ylabel("Y (cm)")
    ax.legend(fontsize=7, loc="upper right")
    return len(w_arr), ref_idx


class PlotSleepNodesEdges2d(BlockBase):
    """Maze graph nodes and directed edges for sleep neural distance."""

    block_type_id = "plot_sleep_nodes_edges_2d"
    display_name  = "Plot Sleep Nodes & Edges 2D"
    category      = "maze2d / Visualization"
    description   = (
        "Plots discretized maze spatial bins (nodes) and directed transition-weight "
        "edges in a zoom region around a reference point, using the sleep neuronal "
        "distance graph.  Use the epoch parameter to show 'pre', 'post', or 'both'."
    )

    inputs = [
        PortDefinition("neural_dist_sleep", "NeuroData[neural_dist_sleep]",
                       "Output of compute_sleep_neural_dist."),
    ]
    outputs = [
        PortDefinition("sleep_nodes_edges_viz", "NeuroData[sleep_nodes_edges_viz]",
                       "Summary (n_edges shown per epoch)."),
    ]
    parameters = [
        ParameterDefinition("epoch",          "enum:pre,post,both", "both",
                            "Which epoch to show: 'pre', 'post', or 'both'."),
        ParameterDefinition("ref_x_cm",       "float",  0.0,
                            "X-coordinate (cm) of the reference point / view centre."),
        ParameterDefinition("ref_y_cm",       "float", -10.0,
                            "Y-coordinate (cm) of the reference point / view centre."),
        ParameterDefinition("zoom_radius_cm", "float",  130.0,
                            "Half-width of the view window around the reference point (cm)."),
        ParameterDefinition("weight_min",     "float",  1.0,
                            "Minimum edge weight to show."),
        ParameterDefinition("weight_max",     "float",  5.0,
                            "Maximum edge weight to show."),
        ParameterDefinition("max_edges",      "int",    800,
                            "Maximum number of edges to draw."),
        ParameterDefinition("random_seed",    "int",    42,
                            "Random seed for edge sampling."),
        ParameterDefinition("show_on_run",    "bool",   True,
                            "Encode figure and display it in the frontend."),
        ParameterDefinition("save_path",      "str",    "",
                            "If non-empty, save figure as PNG to this path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import matplotlib.pyplot as plt

        nd: NeuroData = inputs["neural_dist_sleep"]

        epoch_sel = str(parameters.get("epoch",          "both")).strip().lower()
        ref_x     = float(parameters.get("ref_x_cm",      0.0))
        ref_y     = float(parameters.get("ref_y_cm",     -10.0))
        zoom_r    = float(parameters.get("zoom_radius_cm",130.0))
        w_min     = float(parameters.get("weight_min",    1.0))
        w_max     = float(parameters.get("weight_max",    5.0))
        max_edges = int(parameters.get("max_edges",       800))
        seed      = int(parameters.get("random_seed",     42))
        show      = bool(parameters.get("show_on_run",    True))
        save_path = str(parameters.get("save_path",       ""))

        valid_ij = np.asarray(nd.metadata["valid_ij"])
        bcx      = np.asarray(nd.metadata["bin_centers_x"])
        bcy      = np.asarray(nd.metadata["bin_centers_y"])
        W_pre    = np.asarray(nd.metadata["edge_weights_pre"])
        W_post   = np.asarray(nd.metadata["edge_weights_post"])

        kw = dict(ref_x=ref_x, ref_y=ref_y, zoom_r=zoom_r,
                  w_min=w_min, w_max=w_max, max_edges=max_edges, seed=seed)

        title_suffix = f"weight [{w_min:.1f}, {w_max:.1f}]\ndarker/thinner = stronger"

        if epoch_sel == "both":
            fig, axes = plt.subplots(1, 2, figsize=(12, 6))
            n_pre,  _ = _draw_panel(axes[0], W_pre,  valid_ij, bcx, bcy, **kw)
            n_post, _ = _draw_panel(axes[1], W_post, valid_ij, bcx, bcy, **kw)
            axes[0].set_title(f"Pre-sleep nodes & edges\n{title_suffix}", fontsize=9)
            axes[1].set_title(f"Post-sleep nodes & edges\n{title_suffix}", fontsize=9)
            n_shown = [n_pre, n_post]
        else:
            W = W_pre if epoch_sel == "pre" else W_post
            label = "Pre-sleep" if epoch_sel == "pre" else "Post-sleep"
            fig, ax = plt.subplots(figsize=(6, 6))
            n_shown_v, _ = _draw_panel(ax, W, valid_ij, bcx, bcy, **kw)
            ax.set_title(f"{label} nodes & edges\n{title_suffix}", fontsize=9)
            n_shown = [n_shown_v]

        plt.tight_layout()
        viz = save_and_encode(fig, save_path, show)

        return {
            "sleep_nodes_edges_viz": NeuroData(
                data_type = "sleep_nodes_edges_viz",
                array     = np.array(n_shown, dtype=np.float64),
                metadata  = {"epoch": epoch_sel, "n_edges_shown": n_shown},
            ),
            "_viz": viz,
        }
