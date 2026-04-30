"""Build the 2D maze topology graph and compute all-pairs shortest-path distances.

Mirrors CA_RunSeq_Prep_8Arm category-2 substep-8.

Algorithm
---------
1. Valid nodes = 2D bins where occupancy ≥ min_occupancy_s (from valid_mask).
2. Edges connect every valid bin to its (4- or 8-) neighbouring valid bins.
3. Edge weight = Euclidean distance between bin centres (cm).
4. All-pairs shortest path via Dijkstra (scipy.sparse.csgraph).

Output metadata layout::

    metadata["path_dist"]         → np.ndarray (n_valid, n_valid) float64
    metadata["valid_ij"]          → np.ndarray (n_valid, 2) int  [row, col] in 2D grid
    metadata["valid_bin_centers"] → np.ndarray (n_valid, 2) float  [x_cm, y_cm]
    metadata["bin_centers_x"]     → list[float]  cm
    metadata["bin_centers_y"]     → list[float]  cm
    metadata["bin_size_cm"]       → float
    metadata["n_valid"]           → int
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class BuildMazeGraph2d(BlockBase):
    """Build maze topology graph and compute shortest-path distance matrix."""

    block_type_id = "build_maze_graph_2d"
    display_name  = "Build 2D Maze Graph"
    category      = "maze2d / Analysis"
    description   = (
        "Constructs a weighted graph on the set of visited 2D spatial bins "
        "(8-neighbour connectivity, edge weight = Euclidean distance in cm) and "
        "computes all-pairs shortest-path distances via Dijkstra."
    )

    inputs = [
        PortDefinition("place_maps_2d", "NeuroData[place_maps_2d]",
                       "2D place maps from compute_place_maps_2d."),
    ]
    outputs = [
        PortDefinition("maze_graph_2d", "NeuroData[maze_graph_2d]",
                       "All-pairs shortest-path distance matrix on maze topology."),
    ]
    parameters = [
        ParameterDefinition("connectivity", "int", 8,
                            "Neighbour connectivity: 4 (cardinal) or 8 (cardinal + diagonal)."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import scipy.sparse as sp
        from scipy.sparse.csgraph import shortest_path

        pm: NeuroData = inputs["place_maps_2d"]

        conn        = int(parameters.get("connectivity", 8))
        valid_mask  = np.asarray(pm.metadata["valid_mask"], dtype=bool)
        bcx         = np.asarray(pm.metadata["bin_centers_x"])
        bcy         = np.asarray(pm.metadata["bin_centers_y"])
        bin_size    = float(pm.metadata["bin_size_cm"])

        n_x, n_y = valid_mask.shape
        # Flat indices of valid bins
        valid_flat = np.where(valid_mask.ravel())[0]
        n_valid    = len(valid_flat)

        # Map flat index → position in valid_flat
        flat2valid = np.full(n_x * n_y, -1, dtype=np.int32)
        flat2valid[valid_flat] = np.arange(n_valid, dtype=np.int32)

        valid_ij = np.stack(np.unravel_index(valid_flat, (n_x, n_y)), axis=1)
        valid_bin_centers = np.column_stack([
            bcx[valid_ij[:, 0]],
            bcy[valid_ij[:, 1]],
        ])

        # ── Build sparse adjacency matrix ─────────────────────────────────────
        if conn == 8:
            offsets = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
        else:
            offsets = [(-1,0),(0,-1),(0,1),(1,0)]

        rows, cols, weights = [], [], []

        for vi, (r, c) in enumerate(valid_ij):
            for dr, dc in offsets:
                nr, nc = r + dr, c + dc
                if 0 <= nr < n_x and 0 <= nc < n_y:
                    nf = nr * n_y + nc
                    nvi = flat2valid[nf]
                    if nvi >= 0:
                        # Euclidean distance between bin centres
                        w = np.sqrt((bcx[nr] - bcx[r]) ** 2 + (bcy[nc] - bcy[c]) ** 2)
                        rows.append(vi)
                        cols.append(nvi)
                        weights.append(w)

        graph = sp.csr_matrix(
            (np.array(weights), (np.array(rows), np.array(cols))),
            shape=(n_valid, n_valid),
        )

        # ── All-pairs shortest paths ──────────────────────────────────────────
        path_dist = shortest_path(graph, directed=False, method="D")
        # Unreachable pairs → NaN
        path_dist[np.isinf(path_dist)] = np.nan

        return {
            "maze_graph_2d": NeuroData(
                data_type = "maze_graph_2d",
                array     = path_dist.astype(np.float64),
                metadata  = {
                    "path_dist":          path_dist.astype(np.float64),
                    "valid_ij":           valid_ij,
                    "valid_bin_centers":  valid_bin_centers,
                    "bin_centers_x":      bcx.tolist(),
                    "bin_centers_y":      bcy.tolist(),
                    "bin_size_cm":        bin_size,
                    "n_valid":            n_valid,
                    "n_x":                n_x,
                    "n_y":                n_y,
                },
            )
        }
