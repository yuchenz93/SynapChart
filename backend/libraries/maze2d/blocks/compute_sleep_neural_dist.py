"""Compute neuronal distance between 2D bins from sleep decoded posteriors.

Computes transition matrices and neuronal distances SEPARATELY for pre-run
and post-run sleep, as well as a combined (all-frames) matrix.  The per-frame
posteriors stored by decode_sleep_frames_2d are used to reconstruct
per-epoch soft transition matrices without re-running decoding.

Algorithm (applied to pre, post, and all frames)
-------------------------------------------------
1. Re-accumulate T[epoch][i,j] = Σ_frames Σ_t  post[i,t]·post[j,t+1]
   from the stored per-frame posteriors.
2. Row-normalise T → transition probabilities P.
3. Edge weight: W[i,j] = (−log P[i,j])^gamma.
4. All-pairs shortest path (directed) → neuronal distance matrix.

Output metadata layout::

    metadata["neural_dist_pre"]   → np.ndarray (n_valid, n_valid) float64
    metadata["neural_dist_post"]  → np.ndarray (n_valid, n_valid) float64
    metadata["neural_dist_all"]   → np.ndarray (n_valid, n_valid) float64
    metadata["neural_dist"]       → same as neural_dist_all (default)
    metadata["edge_weights_pre"]  → np.ndarray (n_valid, n_valid) float64
    metadata["edge_weights_post"] → np.ndarray (n_valid, n_valid) float64
    metadata["transition_prob_pre"]  → np.ndarray (n_valid, n_valid) float64
    metadata["transition_prob_post"] → np.ndarray (n_valid, n_valid) float64
    metadata["n_frames_pre"]      → int
    metadata["n_frames_post"]     → int
    metadata["valid_ij"]          → inherited from maze_graph_2d
    metadata["bin_centers_x/y"]   → inherited
    metadata["gamma"]             → float
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


def _build_dist(T: np.ndarray, gamma: float, large_w: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Row-normalise T, compute edge weights, run all-pairs shortest paths."""
    import scipy.sparse as sp
    from scipy.sparse.csgraph import shortest_path

    row_sums = T.sum(axis=1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        P = np.where(row_sums > 0, T / row_sums, 0.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        log_P = np.where(P > 1e-15, -np.log(P), np.nan)
    W = np.where(np.isfinite(log_P), log_P ** gamma, large_w)
    np.fill_diagonal(W, 0.0)

    graph = sp.csr_matrix(W)
    dist = shortest_path(graph, directed=True, method="D")
    dist[np.isinf(dist)] = np.nan
    return dist.astype(np.float64), P, W


class ComputeSleepNeuralDist(BlockBase):
    """Per-epoch neuronal distance matrices from sleep decoded posteriors."""

    block_type_id = "compute_sleep_neural_dist"
    display_name  = "Sleep Neural Distance 2D"
    category      = "maze2d / Analysis"
    description   = (
        "Re-accumulates soft transition matrices separately for pre-run and "
        "post-run sleep frames (using stored posteriors from decode_sleep_frames_2d), "
        "then builds directed Markov graphs and computes all-pairs shortest-path "
        "neuronal distances for pre, post, and combined sleep.  "
        "Downstream visualization blocks use the epoch parameter to select which "
        "distance to display."
    )

    inputs = [
        PortDefinition("decoded_2d_sleep", "NeuroData[decoded_2d_sleep]",
                       "2D decoded sleep frames from decode_sleep_frames_2d "
                       "(epoch_label='all' recommended so both epochs are present)."),
        PortDefinition("maze_graph_2d",    "NeuroData[maze_graph_2d]",
                       "Maze topology graph (valid_ij, bin_centers)."),
    ]
    outputs = [
        PortDefinition("neural_dist_sleep", "NeuroData[neural_dist_sleep]",
                       "Neuronal distance matrices for pre, post, and all sleep."),
    ]
    parameters = [
        ParameterDefinition("gamma",        "float", 2.0,
                            "Exponent for weight transformation W = (-log P)^gamma."),
        ParameterDefinition("large_weight", "float", 1e6,
                            "Edge weight assigned when transition probability = 0."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        ds: NeuroData = inputs["decoded_2d_sleep"]
        mg: NeuroData = inputs["maze_graph_2d"]

        gamma   = float(parameters.get("gamma",        2.0))
        large_w = float(parameters.get("large_weight", 1e6))

        valid_ij = np.asarray(mg.metadata["valid_ij"])
        n_valid  = int(mg.metadata["n_valid"])

        # ── Re-accumulate per-epoch soft transition matrices ───────────────────
        # Each frame stores its full posterior (n_valid, n_tbins) as float32.
        # T[i,j] = Σ_frames Σ_t  post[i,t] · post[j,t+1]
        T_pre  = np.zeros((n_valid, n_valid), dtype=np.float64)
        T_post = np.zeros((n_valid, n_valid), dtype=np.float64)

        frames = ds.metadata.get("frames", [])
        n_pre = 0
        n_post = 0

        for frame in frames:
            ep = str(frame.get("epoch_label", "")).lower()
            post = np.asarray(frame["posterior"], dtype=np.float64)  # (n_valid, n_tbins)
            if post.shape[1] < 2:
                continue
            contrib = post[:, :-1] @ post[:, 1:].T   # (n_valid, n_valid)
            if ep == "pre":
                T_pre  += contrib
                n_pre  += 1
            elif ep == "post":
                T_post += contrib
                n_post += 1
            # "all" epoch_label used only when epoch filter was disabled at decode

        T_all = T_pre + T_post

        # ── Compute distances for each epoch ──────────────────────────────────
        dist_pre,  P_pre,  W_pre  = _build_dist(T_pre,  gamma, large_w)
        dist_post, P_post, W_post = _build_dist(T_post, gamma, large_w)
        dist_all,  P_all,  W_all  = _build_dist(T_all,  gamma, large_w)

        shared_meta = {
            "valid_ij":          valid_ij,
            "valid_bin_centers": mg.metadata["valid_bin_centers"],
            "bin_centers_x":     mg.metadata["bin_centers_x"],
            "bin_centers_y":     mg.metadata["bin_centers_y"],
            "bin_size_cm":       mg.metadata["bin_size_cm"],
            "n_x":               mg.metadata["n_x"],
            "n_y":               mg.metadata["n_y"],
            "n_valid":           n_valid,
            "gamma":             gamma,
        }

        return {
            "neural_dist_sleep": NeuroData(
                data_type = "neural_dist_sleep",
                array     = dist_all,
                metadata  = {
                    # Per-epoch distances (for viz blocks)
                    "neural_dist_pre":      dist_pre,
                    "neural_dist_post":     dist_post,
                    "neural_dist_all":      dist_all,
                    "neural_dist":          dist_all,   # default for generic consumers
                    "edge_weights_pre":     W_pre,
                    "edge_weights_post":    W_post,
                    "edge_weights":         W_all,
                    "transition_prob_pre":  P_pre,
                    "transition_prob_post": P_post,
                    "transition_prob":      P_all,
                    "n_frames_pre":         n_pre,
                    "n_frames_post":        n_post,
                    "n_frames_total":       n_pre + n_post,
                    **shared_meta,
                },
            )
        }
