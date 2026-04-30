"""Compute neuronal distance between 2D bins from waking-rest decoded posteriors.

Mirrors CA_8Arm_AwakeRest_NeuronDist_FramesMG category-1 substep-2.

Algorithm
---------
1. Take the transition count matrix T pre-computed by decode_rest_frames_2d
   (directed argmax transitions across all rest frames).
2. Row-normalise T to transition probabilities P[i,j].
3. Edge weight:  W[i,j] = (−log P[i,j])^gamma  (directed, no symmetrisation).
4. All-pairs shortest path (directed graph) → rest neuronal distance.

Output metadata layout::

    metadata["neural_dist"]       → np.ndarray (n_valid, n_valid) float64
    metadata["transition_counts"] → np.ndarray (n_valid, n_valid) int32
    metadata["valid_ij"]          → inherited from maze_graph
    metadata["valid_bin_centers"] → inherited from maze_graph
    metadata["gamma"]             → float
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class ComputeRestNeuralDist(BlockBase):
    """Neuronal distance matrix from waking-rest decoded posteriors (Markov)."""

    block_type_id = "compute_rest_neural_dist"
    display_name  = "Rest Neural Distance 2D"
    category      = "maze2d / Analysis"
    description   = (
        "Builds a directed Markov graph from argmax-decoded waking-rest frame "
        "posteriors (2D space).  Uses the pre-computed transition count matrix "
        "from decode_rest_frames_2d.  Edge weight = (−log P)^gamma; "
        "all-pairs shortest paths give the neuronal distance matrix."
    )

    inputs = [
        PortDefinition("decoded_2d_rest", "NeuroData[decoded_2d_rest]",
                       "2D decoded rest frames from decode_rest_frames_2d."),
        PortDefinition("maze_graph_2d",   "NeuroData[maze_graph_2d]",
                       "Maze topology graph (valid_ij, bin_centers)."),
    ]
    outputs = [
        PortDefinition("neural_dist_rest", "NeuroData[neural_dist_rest]",
                       "Neuronal distance matrix in valid-bin index space (directed)."),
    ]
    parameters = [
        ParameterDefinition("gamma",        "float", 2.0,
                            "Exponent for weight transformation W = (-log P)^gamma."),
        ParameterDefinition("large_weight", "float", 1e6,
                            "Edge weight assigned when transition count = 0."),
    ]

    # ------------------------------------------------------------------
    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import scipy.sparse as sp
        from scipy.sparse.csgraph import shortest_path

        dr: NeuroData = inputs["decoded_2d_rest"]
        mg: NeuroData = inputs["maze_graph_2d"]

        gamma   = float(parameters.get("gamma",        2.0))
        large_w = float(parameters.get("large_weight", 1e6))

        # ── Soft transition matrix (pre-computed in decode_rest_frames_2d) ──────
        # T[i,j] = Σ_frames Σ_t  post[i,t] · post[j,t+1]  (float64)
        T = np.asarray(dr.metadata["transition_counts"], dtype=np.float64)

        valid_ij = np.asarray(mg.metadata["valid_ij"])
        n_valid  = int(mg.metadata["n_valid"])

        # Sanity check: T must be (n_valid, n_valid)
        if T.shape != (n_valid, n_valid):
            raise ValueError(
                f"compute_rest_neural_dist: transition_counts shape {T.shape} "
                f"does not match n_valid={n_valid} from maze_graph_2d."
            )

        # ── Row-normalise to transition probabilities ─────────────────────────
        row_sums = T.sum(axis=1, keepdims=True)
        with np.errstate(divide="ignore", invalid="ignore"):
            P = np.where(row_sums > 0, T / row_sums, 0.0)

        # ── Edge weights: W = (-log P)^gamma ──────────────────────────────────
        with np.errstate(divide="ignore", invalid="ignore"):
            log_P = np.where(P > 1e-15, -np.log(P), np.nan)
        W = np.where(np.isfinite(log_P), log_P ** gamma, large_w)
        np.fill_diagonal(W, 0.0)

        # ── All-pairs shortest paths (directed) ───────────────────────────────
        graph = sp.csr_matrix(W)
        neural_dist = shortest_path(graph, directed=True, method="D")
        neural_dist[np.isinf(neural_dist)] = np.nan

        return {
            "neural_dist_rest": NeuroData(
                data_type = "neural_dist_rest",
                array     = neural_dist.astype(np.float64),
                metadata  = {
                    "neural_dist":          neural_dist.astype(np.float64),
                    "transition_counts":    T,
                    "transition_prob":      P,        # (n_valid, n_valid) row-normalised
                    "edge_weights":         W,        # (n_valid, n_valid) (-log P)^gamma
                    "valid_ij":             valid_ij,
                    "valid_bin_centers":    mg.metadata["valid_bin_centers"],
                    "bin_centers_x":        mg.metadata["bin_centers_x"],
                    "bin_centers_y":        mg.metadata["bin_centers_y"],
                    "bin_size_cm":          mg.metadata["bin_size_cm"],
                    "gamma":                gamma,
                    "n_valid":              n_valid,
                    "n_x":                  mg.metadata["n_x"],
                    "n_y":                  mg.metadata["n_y"],
                    "diag_total_transitions": int(T.sum()),
                    "diag_n_valid":           n_valid,
                },
            )
        }
