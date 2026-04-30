"""Scatter plot: maze path distance vs neuronal distance (run and rest).

Mirrors CA_8Arm_Run_NeuronDist category-4 substep-1.

For every pair of valid 2D bins the block plots:
  • Actual maze path distance (cm)  vs  Run neuronal distance
  • Actual maze path distance (cm)  vs  Rest neuronal distance

Pearson r and p-value are annotated on each panel.

Output metadata layout::

    metadata["r_run"]       → float  Pearson r (maze vs run neural)
    metadata["p_run"]       → float  p-value
    metadata["r_rest"]      → float  Pearson r (maze vs rest neural)
    metadata["p_rest"]      → float  p-value
    metadata["n_pairs_run"] → int    finite pairs used for run scatter
    metadata["n_pairs_rest"]→ int    finite pairs used for rest scatter
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotNeuralVsMazeDist(BlockBase):
    """Scatter: maze path distance vs run/rest neuronal distance."""

    block_type_id = "plot_neural_vs_maze_dist"
    display_name  = "Neural vs Maze Distance"
    category      = "maze2d / Visualization"
    description   = (
        "Plots maze path distance against run and rest neuronal distance for all "
        "valid bin pairs.  Pearson r and p-value are annotated on each panel."
    )

    inputs = [
        PortDefinition("maze_graph_2d",    "NeuroData[maze_graph_2d]",
                       "Maze topology graph (path_dist, valid_ij)."),
        PortDefinition("neural_dist_run",  "NeuroData[neural_dist_run]",
                       "Run neuronal distance from compute_run_neural_dist."),
        PortDefinition("neural_dist_rest", "NeuroData[neural_dist_rest]",
                       "Rest neuronal distance from compute_rest_neural_dist."),
    ]
    outputs = [
        PortDefinition("dist_comparison", "NeuroData[dist_comparison]",
                       "Correlation statistics (r, p for run and rest)."),
    ]
    parameters = [
        ParameterDefinition("alpha",       "float", 0.3,
                            "Scatter point transparency."),
        ParameterDefinition("dot_size",    "float", 3.0,
                            "Scatter marker size (pt)."),
        ParameterDefinition("show_on_run", "bool",  True,
                            "Encode figure and display it in the frontend."),
        ParameterDefinition("save_path",   "str",   "",
                            "If non-empty, save figure as PNG to this path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import matplotlib.pyplot as plt
        from scipy.stats import pearsonr

        mg:   NeuroData = inputs["maze_graph_2d"]
        ndr:  NeuroData = inputs["neural_dist_run"]
        ndrs: NeuroData = inputs["neural_dist_rest"]

        alpha     = float(parameters.get("alpha",       0.3))
        dot_size  = float(parameters.get("dot_size",    3.0))
        show      = bool(parameters.get("show_on_run",  True))
        save_path = str(parameters.get("save_path",     ""))

        path_dist = np.asarray(mg.metadata["path_dist"],    dtype=np.float64)
        run_dist  = np.asarray(ndr.metadata["neural_dist"], dtype=np.float64)
        rest_dist = np.asarray(ndrs.metadata["neural_dist"],dtype=np.float64)

        n_valid = path_dist.shape[0]

        # Upper triangle (k=1) → all unique bin pairs
        idx_i, idx_j = np.triu_indices(n_valid, k=1)

        pd_vec  = path_dist[idx_i, idx_j]
        rnd_vec = run_dist[idx_i, idx_j]
        # Rest distance is directed; symmetrise for the scatter
        rsd_vec = (rest_dist[idx_i, idx_j] + rest_dist[idx_j, idx_i]) / 2.0

        # ── Run correlation ───────────────────────────────────────────────────
        mask_run = np.isfinite(pd_vec) & np.isfinite(rnd_vec)
        r_run, p_run = (pearsonr(pd_vec[mask_run], rnd_vec[mask_run])
                        if mask_run.sum() > 2 else (np.nan, np.nan))

        # ── Rest correlation ──────────────────────────────────────────────────
        mask_rest = np.isfinite(pd_vec) & np.isfinite(rsd_vec)
        r_rest, p_rest = (pearsonr(pd_vec[mask_rest], rsd_vec[mask_rest])
                          if mask_rest.sum() > 2 else (np.nan, np.nan))

        # ── Figure ────────────────────────────────────────────────────────────
        fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
        fig.suptitle("Maze Path Distance vs Neuronal Distance", fontsize=13)

        for ax, x, y, r, p, label in [
            (axes[0], pd_vec[mask_run],  rnd_vec[mask_run],  r_run,  p_run,  "Run"),
            (axes[1], pd_vec[mask_rest], rsd_vec[mask_rest], r_rest, p_rest, "Waking Rest"),
        ]:
            ax.scatter(x, y, s=dot_size, alpha=alpha, color="steelblue",
                       linewidths=0, rasterized=True)
            ax.set_xlabel("Maze path distance (cm)", fontsize=12)
            ax.set_ylabel(f"{label} neuronal distance (a.u.)", fontsize=12)
            ax.set_title(f"{label} neural distance", fontsize=12)

            r_str = f"{r:.3f}" if np.isfinite(r) else "n/a"
            p_str = f"{p:.2e}" if np.isfinite(p) else "n/a"
            ax.annotate(f"r = {r_str}\np = {p_str}",
                        xy=(0.05, 0.92), xycoords="axes fraction",
                        fontsize=11, va="top",
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8))

        plt.tight_layout()

        viz = save_and_encode(fig, save_path, show)

        return {
            "dist_comparison": NeuroData(
                data_type = "dist_comparison",
                array     = np.array([r_run if np.isfinite(r_run) else np.nan,
                                      r_rest if np.isfinite(r_rest) else np.nan]),
                metadata  = {
                    "r_run":        float(r_run)  if np.isfinite(r_run)  else None,
                    "p_run":        float(p_run)  if np.isfinite(p_run)  else None,
                    "r_rest":       float(r_rest) if np.isfinite(r_rest) else None,
                    "p_rest":       float(p_rest) if np.isfinite(p_rest) else None,
                    "n_pairs_run":  int(mask_run.sum()),
                    "n_pairs_rest": int(mask_rest.sum()),
                },
            ),
            "_viz": viz,
        }
