"""Memoryless Bayesian position decoder — state-aware.

Bins spikes for the full session, then decodes ALL time bins using each
state's tuning curves separately.  Downstream blocks select the correct
state's posterior for their time intervals.

Output metadata layout::

    metadata["posteriors"][state_name]  →  np.ndarray (n_pos_bins × n_time_bins)
    metadata["timestamps"]              →  np.ndarray  (bin-centre times, seconds)
    metadata["bin_centers"]             →  list[float]  (position bin centres, cm)
    metadata["state_keys"]              →  list[str]
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class DecodePosition1d(BlockBase):
    """State-aware Bayesian position decoder for 1D linear maze."""

    block_type_id = "decode_position_1d"
    display_name  = "Decode Position 1D"
    category      = "maze1d / Analysis"
    description   = (
        "Bins population spikes and runs the memoryless Bayesian decoder for "
        "every state using that state's tuning curves.  A single node replaces "
        "the bin_spikes → bayesian_decoder chain for all states simultaneously. "
        "Use bin_size_sec=0.2 for behavioral verification, 0.02 for theta sequences."
    )

    inputs = [
        PortDefinition("spike_data",    "NeuroData[multi_spike_times]",
                       "Multi-cell spike times (full session)."),
        PortDefinition("tuning_curves", "NeuroData[tuning_curves_1d]",
                       "Per-state rate maps from compute_tuning_curves_1d."),
        PortDefinition("position",      "NeuroData[position]",
                       "Linearised 1-D position — used to determine time range."),
        PortDefinition("states",        "NeuroData[states]",
                       "Named states from define_maze_states."),
    ]
    outputs = [
        PortDefinition("decoded", "NeuroData[decoded_1d]",
                       "Per-state posteriors in metadata['posteriors'][state_name]."),
    ]
    parameters = [
        ParameterDefinition("bin_size_sec", "float", 0.02,
                            "Spike count time bin in seconds.  "
                            "0.02 s for theta sequences, 0.2 s for behavioral decoding."),
        ParameterDefinition("prior", "enum:uniform,empirical", "uniform",
                            "Spatial prior (currently only 'uniform' is implemented)."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        spikes:    NeuroData = inputs["spike_data"]
        tc:        NeuroData = inputs["tuning_curves"]
        pos:       NeuroData = inputs["position"]
        states_nd: NeuroData = inputs["states"]

        tau        = float(parameters.get("bin_size_sec", 0.02))

        spike_times        = spikes.array
        cell_ids_per_spike = np.asarray(spikes.metadata.get("spike_cell_ids", []))
        cell_ids = np.array(
            spikes.metadata.get("cell_ids",
                                sorted(np.unique(cell_ids_per_spike).tolist())),
            dtype=int,
        )

        pos_1d = pos.array.flatten()
        pos_ts = pos.timestamps
        pos_sr = pos.sampling_rate or 39.0
        if pos_ts is None:
            pos_ts = np.arange(len(pos_1d)) / pos_sr

        t_start = float(pos_ts[0])
        t_end   = float(pos_ts[-1])

        # ── Build time bins (shared across all states) ────────────────────────
        bin_edges  = np.arange(t_start, t_end + tau, tau)
        bin_times  = (bin_edges[:-1] + bin_edges[1:]) / 2.0   # bin centres
        n_time     = len(bin_times)

        # ── Bin spikes into (n_cells, n_time_bins) ────────────────────────────
        spike_matrix = np.zeros((len(cell_ids), n_time), dtype=np.float32)
        for i, cid in enumerate(cell_ids):
            if len(cell_ids_per_spike) != len(spike_times):
                continue
            st = spike_times[cell_ids_per_spike == cid]
            if len(st) == 0:
                continue
            counts, _ = np.histogram(st, bins=bin_edges)
            spike_matrix[i] = counts.astype(np.float32)

        # ── Shared position bin setup ─────────────────────────────────────────
        bin_centers    = tc.metadata.get("bin_centers", [])
        rate_maps_all  = tc.metadata.get("rate_maps", {})
        state_keys     = tc.metadata.get("state_keys", list(rate_maps_all.keys()))

        eps       = 1e-10
        posteriors: dict[str, np.ndarray] = {}

        for sname in state_keys:
            rate_maps = rate_maps_all.get(sname)
            if rate_maps is None:
                continue

            n_cells, n_pos = rate_maps.shape
            log_tc  = np.log(np.maximum(rate_maps, eps))   # (n_cells, n_pos)

            # Vectorised log-posterior: (n_time, n_pos)
            spk     = spike_matrix[:n_cells]               # align cell counts
            term1   = spk.T @ log_tc                       # (n_time, n_pos)
            term2   = tau * rate_maps.sum(axis=0)          # (n_pos,)
            lp      = term1 - term2                        # (n_time, n_pos)

            # Numerically stable normalisation per time bin
            lp -= lp.max(axis=1, keepdims=True)
            post_T = np.exp(lp)
            col_sums = post_T.sum(axis=1, keepdims=True)
            col_sums = np.where(col_sums > 0, col_sums, 1.0)
            post_T  /= col_sums

            posteriors[sname] = post_T.T.astype(np.float32)  # (n_pos, n_time)

        first_key  = state_keys[0] if state_keys else None
        first_post = posteriors[first_key] if first_key and first_key in posteriors \
                     else np.zeros((1, n_time), dtype=np.float32)

        return {
            "decoded": NeuroData(
                data_type  = "decoded_1d",
                array      = first_post,
                timestamps = bin_times,
                metadata   = {
                    "posteriors":   posteriors,
                    "state_keys":   state_keys,
                    "bin_centers":  bin_centers,
                    "bin_size_sec": tau,
                    "n_pos_bins":   len(bin_centers),
                    "n_time_bins":  n_time,
                    "t_start":      t_start,
                    "t_end":        t_end,
                    "pos_min":      tc.metadata.get("pos_min", 0.0),
                    "pos_max":      tc.metadata.get("pos_max", 160.0),
                    "bin_width_cm": tc.metadata.get("bin_width_cm", 1.0),
                },
            )
        }
