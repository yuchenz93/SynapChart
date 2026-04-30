"""Scatter plot: maze path distance vs sleep neuronal distance (pre and post).

Takes a single neural_dist_sleep from compute_sleep_neural_dist, which
contains both pre- and post-sleep distance matrices internally.

For every pair of valid 2D bins the block plots:
  • Actual maze path distance (cm)  vs  Pre-sleep neuronal distance
  • Actual maze path distance (cm)  vs  Post-sleep neuronal distance

Pearson r and p-value are annotated on each panel.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotSleepVsMazeDist(BlockBase):
    """Scatter: maze path distance vs pre- and post-sleep neuronal distance."""

    block_type_id = "plot_sleep_vs_maze_dist"
    display_name  = "Sleep Neural vs Maze Distance"
    category      = "maze2d / Visualization"
    description   = (
        "Plots maze path distance against pre-run and post-run sleep neuronal "
        "distance for all valid bin pairs.  Both panels come from a single "
        "compute_sleep_neural_dist output.  Pearson r and p-value are annotated."
    )

    inputs = [
        PortDefinition("maze_graph_2d",    "NeuroData[maze_graph_2d]",
                       "Maze topology graph (path_dist, valid_ij)."),
        PortDefinition("neural_dist_sleep", "NeuroData[neural_dist_sleep]",
                       "Sleep neural distances (pre + post) from compute_sleep_neural_dist."),
    ]
    outputs = [
        PortDefinition("sleep_dist_comparison", "NeuroData[sleep_dist_comparison]",
                       "Correlation statistics (r, p for pre and post sleep)."),
    ]
    parameters = [
        ParameterDefinition("alpha",       "float", 0.3,
                            "Scatter point transparency."),
        ParameterDefinition("dot_size",    "float", 3.0,
                            "Scatter marker size (pt)."),
        ParameterDefinition("color_pre",   "str",   "#4f86c6",
                            "Dot colour for the pre-sleep panel."),
        ParameterDefinition("color_post",  "str",   "#e07b39",
                            "Dot colour for the post-sleep panel."),
        ParameterDefinition("show_on_run", "bool",  True,
                            "Encode figure and display it in the frontend."),
        ParameterDefinition("save_path",   "str",   "",
                            "If non-empty, save figure as PNG to this path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import matplotlib.pyplot as plt
        from scipy.stats import pearsonr

        mg:  NeuroData = inputs["maze_graph_2d"]
        nd:  NeuroData = inputs["neural_dist_sleep"]

        alpha      = float(parameters.get("alpha",      0.3))
        dot_size   = float(parameters.get("dot_size",   3.0))
        color_pre  = str(parameters.get("color_pre",   "#4f86c6"))
        color_post = str(parameters.get("color_post",  "#e07b39"))
        show       = bool(parameters.get("show_on_run", True))
        save_path  = str(parameters.get("save_path",   ""))

        path_dist  = np.asarray(mg.metadata["path_dist"],         dtype=np.float64)
        pre_dist   = np.asarray(nd.metadata["neural_dist_pre"],   dtype=np.float64)
        post_dist  = np.asarray(nd.metadata["neural_dist_post"],  dtype=np.float64)

        n_pre_frames  = int(nd.metadata.get("n_frames_pre",  0))
        n_post_frames = int(nd.metadata.get("n_frames_post", 0))

        n_valid = path_dist.shape[0]
        idx_i, idx_j = np.triu_indices(n_valid, k=1)

        pd_vec   = path_dist[idx_i, idx_j]
        pre_vec  = (pre_dist[idx_i, idx_j]  + pre_dist[idx_j, idx_i])  / 2.0
        post_vec = (post_dist[idx_i, idx_j] + post_dist[idx_j, idx_i]) / 2.0

        mask_pre  = np.isfinite(pd_vec) & np.isfinite(pre_vec)
        mask_post = np.isfinite(pd_vec) & np.isfinite(post_vec)

        r_pre,  p_pre  = (pearsonr(pd_vec[mask_pre],  pre_vec[mask_pre])
                          if mask_pre.sum() > 2 else (np.nan, np.nan))
        r_post, p_post = (pearsonr(pd_vec[mask_post], post_vec[mask_post])
                          if mask_post.sum() > 2 else (np.nan, np.nan))

        fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
        fig.suptitle("Maze Path Distance vs Sleep Neuronal Distance", fontsize=13)

        for ax, x, y, r, p, label, color, mask, n_fr in [
            (axes[0], pd_vec[mask_pre],  pre_vec[mask_pre],
             r_pre,  p_pre,  f"Pre-sleep  ({n_pre_frames} frames)",  color_pre,  mask_pre,  n_pre_frames),
            (axes[1], pd_vec[mask_post], post_vec[mask_post],
             r_post, p_post, f"Post-sleep  ({n_post_frames} frames)", color_post, mask_post, n_post_frames),
        ]:
            ax.scatter(x, y, s=dot_size, alpha=alpha, color=color,
                       linewidths=0, rasterized=True)
            ax.set_xlabel("Maze path distance (cm)", fontsize=12)
            ax.set_ylabel(f"Neural distance (a.u.)", fontsize=12)
            ax.set_title(label, fontsize=12)
            r_str = f"{r:.3f}" if np.isfinite(r) else "n/a"
            p_str = f"{p:.2e}" if np.isfinite(p) else "n/a"
            ax.annotate(f"r = {r_str}\np = {p_str}",
                        xy=(0.05, 0.92), xycoords="axes fraction",
                        fontsize=11, va="top",
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8))

        plt.tight_layout()
        viz = save_and_encode(fig, save_path, show)

        return {
            "sleep_dist_comparison": NeuroData(
                data_type = "sleep_dist_comparison",
                array     = np.array([
                    r_pre  if np.isfinite(r_pre)  else np.nan,
                    r_post if np.isfinite(r_post) else np.nan,
                ]),
                metadata  = {
                    "r_pre":          float(r_pre)  if np.isfinite(r_pre)  else None,
                    "p_pre":          float(p_pre)  if np.isfinite(p_pre)  else None,
                    "r_post":         float(r_post) if np.isfinite(r_post) else None,
                    "p_post":         float(p_post) if np.isfinite(p_post) else None,
                    "n_pairs_pre":    int(mask_pre.sum()),
                    "n_pairs_post":   int(mask_post.sum()),
                    "n_frames_pre":   n_pre_frames,
                    "n_frames_post":  n_post_frames,
                },
            ),
            "_viz": viz,
        }
