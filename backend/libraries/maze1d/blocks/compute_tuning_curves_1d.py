"""Compute population tuning curves for every state in a NeuroData[states] object.

For each state the position samples and spikes are restricted to the union of
that state's time intervals (plus an optional speed threshold).  All states
share the same position bins so downstream blocks can compare across states.

Output metadata layout::

    metadata["rate_maps"][state_name]  →  np.ndarray (n_cells × n_bins)
    metadata["state_keys"]             →  list[str]
    metadata["cell_ids"]               →  list[int]
    metadata["bin_centers"]            →  list[float]  (cm)
    metadata["bin_width_cm"]           →  float
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class ComputeTuningCurves1d(BlockBase):
    """Compute per-state population tuning curves for a 1D linear maze."""

    block_type_id = "compute_tuning_curves_1d"
    display_name  = "Tuning Curves 1D"
    category      = "maze1d / Analysis"
    description   = (
        "Computes firing-rate vs linearised-position tuning curves for every "
        "cell and every state.  Position samples and spikes are restricted to "
        "the union of each state's time intervals.  All states share the same "
        "position bins."
    )

    inputs = [
        PortDefinition("spike_data", "NeuroData[multi_spike_times]",
                       "Multi-cell spike times (full session)."),
        PortDefinition("position",   "NeuroData[position]",
                       "Linearised 1-D position with timestamps (cm)."),
        PortDefinition("states",     "NeuroData[states]",
                       "Named states from define_maze_states."),
    ]
    outputs = [
        PortDefinition("tuning_curves", "NeuroData[tuning_curves_1d]",
                       "Per-state rate maps in metadata['rate_maps'][state_name]."),
    ]
    parameters = [
        ParameterDefinition("n_bins",          "int",   80,
                            "Number of position bins (80 bins / 160 cm = 2 cm per bin)."),
        ParameterDefinition("smooth_sigma",    "float", 1.5,
                            "Gaussian smoothing σ in bins (1.5 bins × 2 cm = 3 cm std)."),
        ParameterDefinition("min_occupancy",   "float", 0.1,
                            "Minimum occupancy (s) per bin to compute a rate."),
        ParameterDefinition("speed_threshold", "float", 5.0,
                            "Minimum speed (cm/s) to include a position sample."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        from scipy.ndimage import gaussian_filter1d

        spikes:    NeuroData = inputs["spike_data"]
        pos:       NeuroData = inputs["position"]
        states_nd: NeuroData = inputs["states"]

        n_bins    = int(parameters.get("n_bins",          80))
        sigma     = float(parameters.get("smooth_sigma",    1.5))
        min_occ   = float(parameters.get("min_occupancy",   0.1))
        speed_thr = float(parameters.get("speed_threshold", 5.0))

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
        dt = 1.0 / pos_sr

        speed = np.abs(np.gradient(pos_1d, pos_ts))

        # Shared position bins (full track extent)
        p_min, p_max = float(np.nanmin(pos_1d)), float(np.nanmax(pos_1d))
        bins        = np.linspace(p_min, p_max, n_bins + 1)
        bin_centers = (bins[:-1] + bins[1:]) / 2.0

        states_dict = states_nd.metadata.get("states", {})
        rate_maps_by_state: dict[str, np.ndarray] = {}

        for state_name, state in states_dict.items():
            intervals = state["intervals"]

            # Time mask: union of lap intervals
            interval_mask = np.zeros(len(pos_ts), dtype=bool)
            for t0, t1 in intervals:
                interval_mask |= (pos_ts >= t0) & (pos_ts <= t1)

            run_mask = interval_mask & (speed >= speed_thr) if speed_thr > 0 else interval_mask

            # Occupancy (seconds per bin)
            occ, _ = np.histogram(pos_1d[run_mask], bins=bins)
            occ_s  = occ * dt

            rate_maps = np.zeros((len(cell_ids), n_bins), dtype=np.float32)

            for i, cid in enumerate(cell_ids):
                if len(cell_ids_per_spike) != len(spike_times):
                    continue
                st = spike_times[cell_ids_per_spike == cid]
                if len(st) == 0:
                    continue

                sp_pos   = np.interp(st, pos_ts, pos_1d,  left=np.nan, right=np.nan)
                sp_speed = np.interp(st, pos_ts, speed,   left=0.0,    right=0.0)

                # Restrict spikes to state intervals
                in_interval = np.zeros(len(st), dtype=bool)
                for t0, t1 in intervals:
                    in_interval |= (st >= t0) & (st <= t1)

                valid = ~np.isnan(sp_pos) & in_interval
                if speed_thr > 0:
                    valid &= (sp_speed >= speed_thr)

                counts, _ = np.histogram(sp_pos[valid], bins=bins)
                with np.errstate(invalid="ignore", divide="ignore"):
                    rate = np.where(occ_s >= min_occ, counts / occ_s, 0.0)
                if sigma > 0:
                    rate = gaussian_filter1d(rate.astype(float), sigma=sigma)

                rate_maps[i] = rate.astype(np.float32)

            rate_maps_by_state[state_name] = rate_maps

        state_keys = list(rate_maps_by_state.keys())
        first_map  = rate_maps_by_state[state_keys[0]] if state_keys else np.zeros((len(cell_ids), n_bins))

        return {
            "tuning_curves": NeuroData(
                data_type     = "tuning_curves_1d",
                array         = first_map,
                timestamps    = bin_centers.astype(np.float64),
                channel_names = [str(c) for c in cell_ids],
                metadata      = {
                    "rate_maps":    rate_maps_by_state,
                    "state_keys":   state_keys,
                    "cell_ids":     cell_ids.tolist(),
                    "pyr_ids":      spikes.metadata.get("pyr_ids", []),
                    "int_ids":      spikes.metadata.get("int_ids", []),
                    "n_bins":       n_bins,
                    "pos_min":      p_min,
                    "pos_max":      p_max,
                    "bin_centers":  bin_centers.tolist(),
                    "bin_width_cm": float((p_max - p_min) / n_bins),
                },
            )
        }
