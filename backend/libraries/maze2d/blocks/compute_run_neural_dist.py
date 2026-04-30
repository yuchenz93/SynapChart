"""Compute neuronal distance between 2D bins from run-state place maps.

Mirrors CA_8Arm_Run_NeuronDist category-2 substep-2
(CA_8arm_Run_2DNeuralDistance_WGraph / GetNDistFrom2DMap_WG).

Algorithm
---------
1. For each valid maze bin extract the population-rate vector (n_cells,).
2. Z-score each cell's rate vector:  z = (r - μ) / max(floor, σ).
3. Compute pairwise Pearson correlation between all valid-bin pop-vectors → S[i,j].
4. Clip to [0, 1]:  P[i,j] = max(0, S[i,j]).
5. Edge weight:  W[i,j] = (−log P[i,j])^gamma  (W→∞ where P=0 → disconnected).
6. All-pairs shortest path (undirected weighted complete graph) → neural distance.

Output metadata layout::

    metadata["neural_dist"]       → np.ndarray (n_valid, n_valid) float64
    metadata["similarity"]        → np.ndarray (n_valid, n_valid) Pearson r
    metadata["valid_ij"]          → inherited from maze_graph
    metadata["valid_bin_centers"] → inherited from maze_graph
    metadata["gamma"]             → float
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class ComputeRunNeuralDist(BlockBase):
    """Neuronal distance matrix from run-state 2D place maps."""

    block_type_id = "compute_run_neural_dist"
    display_name  = "Run Neural Distance 2D"
    category      = "maze2d / Analysis"
    description   = (
        "Computes pairwise neuronal distance between visited 2D maze bins using "
        "z-scored population vectors from run-state place maps.  Similarity is "
        "Pearson correlation, converted to edge weights via −log(sim)^gamma, and "
        "all-pairs shortest paths give the final distance matrix."
    )

    inputs = [
        PortDefinition("place_maps_2d", "NeuroData[place_maps_2d]",
                       "2D place maps from compute_place_maps_2d."),
        PortDefinition("maze_graph_2d", "NeuroData[maze_graph_2d]",
                       "Maze topology graph from build_maze_graph_2d."),
    ]
    outputs = [
        PortDefinition("neural_dist_run", "NeuroData[neural_dist_run]",
                       "Neuronal distance matrix in valid-bin index space."),
    ]
    parameters = [
        ParameterDefinition("gamma",        "float", 2.0,
                            "Exponent for weight transformation W = (-log P)^gamma."),
        ParameterDefinition("zscore_floor", "float", 0.2,
                            "Minimum std used in z-score to prevent outlier domination."),
        ParameterDefinition("large_weight", "float", 1e6,
                            "Edge weight assigned when correlation ≤ 0 (disconnected)."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import scipy.sparse as sp
        from scipy.sparse.csgraph import shortest_path

        pm:  NeuroData = inputs["place_maps_2d"]
        mg:  NeuroData = inputs["maze_graph_2d"]

        gamma       = float(parameters.get("gamma",        2.0))
        floor_std   = float(parameters.get("zscore_floor", 0.2))
        large_w     = float(parameters.get("large_weight", 1e6))

        rate_maps   = np.asarray(pm.metadata["maps"],    dtype=np.float64)  # (n_cells, n_x, n_y)
        valid_ij    = np.asarray(mg.metadata["valid_ij"])                   # (n_valid, 2)
        n_valid     = int(mg.metadata["n_valid"])

        # ── Population vectors for each valid bin ─────────────────────────────
        pvecs = np.zeros((n_valid, rate_maps.shape[0]), dtype=np.float64)
        for vi, (r, c) in enumerate(valid_ij):
            pvecs[vi] = rate_maps[:, r, c]
        # Treat NaN firing rates as 0
        pvecs = np.nan_to_num(pvecs, nan=0.0)

        # ── Z-score per cell across valid bins ────────────────────────────────
        mu  = pvecs.mean(axis=0)                       # (n_cells,)
        sig = pvecs.std(axis=0)
        sig = np.maximum(sig, floor_std)
        zvecs = (pvecs - mu) / sig                     # (n_valid, n_cells)

        # ── Pairwise Pearson correlation ──────────────────────────────────────
        # Normalise rows to unit vectors for fast dot-product correlation
        norms = np.linalg.norm(zvecs, axis=1, keepdims=True)
        norms = np.where(norms > 1e-12, norms, 1.0)
        znorm = zvecs / norms                          # (n_valid, n_cells)
        sim   = znorm @ znorm.T                        # (n_valid, n_valid) Pearson r
        np.clip(sim, -1.0, 1.0, out=sim)

        # ── Edge weights: W = (-log P)^gamma ──────────────────────────────────
        P = np.clip(sim, 0.0, 1.0)                    # clip negative corr to 0
        with np.errstate(divide="ignore", invalid="ignore"):
            log_P = np.where(P > 1e-15, -np.log(P), np.nan)
        W = np.where(np.isfinite(log_P), log_P ** gamma, large_w)
        np.fill_diagonal(W, 0.0)

        # ── All-pairs shortest paths (complete graph) ─────────────────────────
        graph = sp.csr_matrix(W)
        neural_dist = shortest_path(graph, directed=False, method="D")
        neural_dist[np.isinf(neural_dist)] = np.nan

        return {
            "neural_dist_run": NeuroData(
                data_type = "neural_dist_run",
                array     = neural_dist.astype(np.float64),
                metadata  = {
                    "neural_dist":        neural_dist.astype(np.float64),
                    "similarity":         sim.astype(np.float32),
                    "valid_ij":           valid_ij,
                    "valid_bin_centers":  mg.metadata["valid_bin_centers"],
                    "bin_centers_x":      mg.metadata["bin_centers_x"],
                    "bin_centers_y":      mg.metadata["bin_centers_y"],
                    "bin_size_cm":        mg.metadata["bin_size_cm"],
                    "gamma":              gamma,
                    "n_valid":            n_valid,
                    "n_x":                mg.metadata["n_x"],
                    "n_y":                mg.metadata["n_y"],
                },
            )
        }
