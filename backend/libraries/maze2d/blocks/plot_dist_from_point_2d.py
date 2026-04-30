"""Visualize maze path distance and neuronal distances from a reference 2D bin.

Mirrors CA_8Arm_Run_NeuronDist category-2 substep-4.

Picks a reference bin (random or specified by index) and renders three
side-by-side 2D heatmaps:
  1. Maze path distance from the reference bin.
  2. Run neuronal distance from the reference bin.
  3. Waking-rest neuronal distance (symmetrised) from the reference bin.

The reference bin is marked with a white/black cross on all panels.

Output metadata layout::

    metadata["ref_bin_idx"]       → int         index into valid_ij
    metadata["ref_xy_cm"]         → [x, y]      cm of the reference bin centre
    metadata["path_dist_from_ref"]→ list[float] maze path dist from ref to each valid bin
    metadata["run_dist_from_ref"] → list[float] run neural dist from ref
    metadata["rest_dist_from_ref"]→ list[float] rest neural dist (symmetrised) from ref
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotDistFromPoint2d(BlockBase):
    """2D heatmaps of maze/run/rest distances from a random reference bin."""

    block_type_id = "plot_dist_from_point_2d"
    display_name  = "Distance from Point 2D"
    category      = "maze2d / Visualization"
    description   = (
        "Chooses a reference valid maze bin (random or fixed index) and draws "
        "three 2D heatmaps showing maze path distance, run neuronal distance, "
        "and waking-rest neuronal distance from that reference bin."
    )

    inputs = [
        PortDefinition("maze_graph_2d",    "NeuroData[maze_graph_2d]",
                       "Maze topology graph."),
        PortDefinition("neural_dist_run",  "NeuroData[neural_dist_run]",
                       "Run neuronal distance matrix."),
        PortDefinition("neural_dist_rest", "NeuroData[neural_dist_rest]",
                       "Rest neuronal distance matrix (directed)."),
    ]
    outputs = [
        PortDefinition("dist_from_point", "NeuroData[dist_from_point]",
                       "Reference bin info and per-bin distance vectors."),
    ]
    parameters = [
        ParameterDefinition("ref_bin_idx", "int",  -1,
                            "Index into valid_ij for the reference bin.  "
                            "-1 = pick randomly."),
        ParameterDefinition("random_seed", "int",  42,
                            "Seed for random reference bin selection."),
        ParameterDefinition("cmap",        "str",  "viridis",
                            "Colormap for the heatmaps."),
        ParameterDefinition("show_on_run", "bool", True,
                            "Encode figure and display it in the frontend."),
        ParameterDefinition("save_path",   "str",  "",
                            "If non-empty, save figure as PNG to this path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import matplotlib.pyplot as plt

        mg:   NeuroData = inputs["maze_graph_2d"]
        ndr:  NeuroData = inputs["neural_dist_run"]
        ndrs: NeuroData = inputs["neural_dist_rest"]

        ref_bin_idx = int(parameters.get("ref_bin_idx", -1))
        seed        = int(parameters.get("random_seed", 42))
        cmap        = str(parameters.get("cmap",        "viridis"))
        show        = bool(parameters.get("show_on_run", True))
        save_path   = str(parameters.get("save_path",   ""))

        valid_ij      = np.asarray(mg.metadata["valid_ij"])            # (n_valid, 2)
        valid_bc      = np.asarray(mg.metadata["valid_bin_centers"])   # (n_valid, 2) cm
        path_dist     = np.asarray(mg.metadata["path_dist"],    dtype=np.float64)
        run_dist      = np.asarray(ndr.metadata["neural_dist"], dtype=np.float64)
        rest_dist_raw = np.asarray(ndrs.metadata["neural_dist"],dtype=np.float64)
        bcx           = np.asarray(mg.metadata["bin_centers_x"])
        bcy           = np.asarray(mg.metadata["bin_centers_y"])
        n_x           = int(mg.metadata["n_x"])
        n_y           = int(mg.metadata["n_y"])
        n_valid       = int(mg.metadata["n_valid"])

        # Symmetrise directed rest distance for visualisation
        rest_dist = (rest_dist_raw + rest_dist_raw.T) / 2.0

        # ── Choose reference bin ──────────────────────────────────────────────
        if ref_bin_idx < 0 or ref_bin_idx >= n_valid:
            rng = np.random.default_rng(seed)
            ref_bin_idx = int(rng.integers(0, n_valid))

        ref_xy = valid_bc[ref_bin_idx]          # [x_cm, y_cm]

        # Distance row from reference bin to all valid bins
        pd_vec  = path_dist[ref_bin_idx, :]
        rnd_vec = run_dist[ref_bin_idx, :]
        rsd_vec = rest_dist[ref_bin_idx, :]

        # ── Scatter valid-bin vectors onto 2D grid ────────────────────────────
        def _to_grid(vec: np.ndarray) -> np.ndarray:
            grid = np.full((n_x, n_y), np.nan)
            for vi, (r, c) in enumerate(valid_ij):
                grid[r, c] = vec[vi]
            return grid

        grid_path = _to_grid(pd_vec)
        grid_run  = _to_grid(rnd_vec)
        grid_rest = _to_grid(rsd_vec)

        # Spatial extent: [x_left, x_right, y_bottom, y_top]
        dx = float(bcx[1] - bcx[0]) if len(bcx) > 1 else 4.0
        dy = float(bcy[1] - bcy[0]) if len(bcy) > 1 else 4.0
        extent = [float(bcx[0])  - dx / 2,
                  float(bcx[-1]) + dx / 2,
                  float(bcy[0])  - dy / 2,
                  float(bcy[-1]) + dy / 2]

        # Reference point in physical coordinates
        ref_row, ref_col = valid_ij[ref_bin_idx]
        ref_x_plot = float(bcx[ref_row])
        ref_y_plot = float(bcy[ref_col])

        # ── Figure ────────────────────────────────────────────────────────────
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        fig.suptitle(
            f"Distances from reference bin #{ref_bin_idx}  "
            f"({ref_xy[0]:.1f}, {ref_xy[1]:.1f}) cm",
            fontsize=13,
        )

        panels = [
            ("Maze path distance (cm)",              grid_path),
            ("Run neuronal distance (a.u.)",          grid_run),
            ("Waking-rest neuronal distance (a.u.)", grid_rest),
        ]

        for ax, (title, grid) in zip(axes, panels):
            # Transpose: grid[row=x, col=y] → imshow wants [y, x] with origin=lower
            im = ax.imshow(
                grid.T,
                origin="lower",
                extent=extent,
                aspect="equal",
                cmap=cmap,
                interpolation="nearest",
            )
            ax.set_title(title, fontsize=11)
            ax.set_xlabel("X (cm)", fontsize=10)
            ax.set_ylabel("Y (cm)", fontsize=10)
            plt.colorbar(im, ax=ax, shrink=0.75, pad=0.02)

            # Cross marking the reference bin
            ax.plot(ref_x_plot, ref_y_plot, "w+", ms=14, mew=2.5, zorder=5)
            ax.plot(ref_x_plot, ref_y_plot, "k+", ms=9,  mew=1.0, zorder=6)

        plt.tight_layout()

        viz = save_and_encode(fig, save_path, show)

        return {
            "dist_from_point": NeuroData(
                data_type = "dist_from_point",
                array     = np.array([float(ref_bin_idx)]),
                metadata  = {
                    "ref_bin_idx":         ref_bin_idx,
                    "ref_xy_cm":           ref_xy.tolist(),
                    "path_dist_from_ref":  pd_vec.tolist(),
                    "run_dist_from_ref":   rnd_vec.tolist(),
                    "rest_dist_from_ref":  rsd_vec.tolist(),
                    "valid_ij":            valid_ij.tolist(),
                },
            ),
            "_viz": viz,
        }
