"""Compute 1-D tuning curves for all cells in a population.

Output is a (n_cells × n_bins) firing-rate matrix stored as
NeuroData[tuning_curves_population].  Compatible with bayesian_decoder.

When a ``laps`` port is connected the computation is restricted to the
running periods in the selected direction.  With direction='both' all laps
are used; with direction='1' or direction='2' only the corresponding
directional laps are included.

Default parameters assume position is in cm (from load_crcns_session with
track_length_cm=160):
  n_bins = 80   →  2 cm per bin
  smooth_sigma = 1.5 bins  →  ~3 cm Gaussian smoothing std
  speed_threshold = 5 cm/s
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class ComputePopulationTuningCurves(BlockBase):
    """Compute 1-D tuning curves for all cells from multi-cell spike data."""

    block_type_id = "compute_population_tuning_curves"
    display_name  = "Population Tuning Curves"
    category      = "Spikes"
    description   = (
        "Computes a firing-rate vs linearised-position tuning curve for every "
        "cell.  When laps are provided, analysis is restricted to the selected "
        "direction.  Default parameters assume position in cm with a 160 cm track "
        "(2 cm bins, 3 cm Gaussian smoothing)."
    )

    inputs = [
        PortDefinition("spike_data", "NeuroData[multi_spike_times]",
                       "Multi-cell spike times with cell IDs in metadata."),
        PortDefinition("position",   "NeuroData[position]",
                       "Linearised 1-D position with timestamps (cm)."),
        PortDefinition("laps",       "NeuroData[laps]",
                       "Running laps from detect_run_laps. "
                       "If connected, analysis is restricted to running periods.",
                       required=False),
    ]
    outputs = [
        PortDefinition("tuning_curves", "NeuroData[tuning_curves_population]",
                       "(n_cells × n_bins) firing-rate matrix. "
                       "channel_names = cell ID strings."),
    ]
    parameters = [
        ParameterDefinition("n_bins",         "int",   80,
                            "Number of position bins. "
                            "80 bins over 160 cm = 2 cm per bin."),
        ParameterDefinition("smooth_sigma",   "float",  1.5,
                            "Gaussian smoothing σ in bins. "
                            "1.5 bins × 2 cm/bin = 3 cm smoothing std."),
        ParameterDefinition("min_occupancy",  "float",  0.1,
                            "Minimum occupancy (seconds) per bin to compute rate."),
        ParameterDefinition("speed_threshold","float",  5.0,
                            "Minimum speed (cm/s) to include a position sample. "
                            "0 = no speed filter. Applied on top of laps filter."),
        ParameterDefinition("direction",
                            "enum:both,1,2", "both",
                            "Which running direction to include. "
                            "'1' = descending, '2' = ascending, 'both' = all laps."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        from scipy.ndimage import gaussian_filter1d

        spikes: NeuroData = inputs["spike_data"]
        pos:    NeuroData = inputs["position"]
        laps_nd           = inputs.get("laps")

        n_bins    = int(parameters.get("n_bins",           80))
        sigma     = float(parameters.get("smooth_sigma",    1.5))
        min_occ   = float(parameters.get("min_occupancy",   0.1))
        speed_thr = float(parameters.get("speed_threshold", 5.0))
        direction = str(parameters.get("direction",         "both"))

        spike_times        = spikes.array
        cell_ids_per_spike = np.asarray(spikes.metadata.get("spike_cell_ids", []))
        cell_ids           = np.array(
            spikes.metadata.get("cell_ids",
                                sorted(np.unique(cell_ids_per_spike).tolist())),
            dtype=int,
        )

        pos_1d = pos.array.flatten()
        pos_ts = pos.timestamps
        pos_sr = pos.sampling_rate or float(1.0 / np.median(np.diff(pos.timestamps)))

        # Speed (cm/s when position is in cm)
        speed = np.abs(np.gradient(pos_1d, pos_ts)) if pos_ts is not None else \
                np.abs(np.gradient(pos_1d)) * pos_sr

        # ── Build time mask: speed filter ─────────────────────────────────────
        if speed_thr > 0:
            run_mask = speed >= speed_thr
        else:
            run_mask = np.ones(len(pos_1d), dtype=bool)

        # ── Restrict to lap periods if laps provided ──────────────────────────
        if laps_nd is not None:
            lap_list = laps_nd.metadata.get("laps", [])
            # Filter by direction
            if direction == "1":
                lap_list = [l for l in lap_list if l["direction"] == 1]
            elif direction == "2":
                lap_list = [l for l in lap_list if l["direction"] == 2]

            lap_mask = np.zeros(len(pos_ts), dtype=bool)
            for lap in lap_list:
                lap_mask |= (pos_ts >= lap["t_start"]) & (pos_ts <= lap["t_end"])
            run_mask &= lap_mask

        pos_run = pos_1d[run_mask]
        ts_run  = pos_ts[run_mask] if pos_ts is not None else None

        # ── Position bins ─────────────────────────────────────────────────────
        p_min, p_max = float(np.nanmin(pos_1d)), float(np.nanmax(pos_1d))
        bins         = np.linspace(p_min, p_max, n_bins + 1)
        bin_centers  = (bins[:-1] + bins[1:]) / 2.0
        dt           = 1.0 / pos_sr

        # Occupancy from running periods only
        occ, _ = np.histogram(pos_run, bins=bins)
        occ_s  = occ * dt   # seconds

        # ── Rate map per cell ─────────────────────────────────────────────────
        rate_maps = np.zeros((len(cell_ids), n_bins), dtype=np.float32)

        for i, cid in enumerate(cell_ids):
            if len(cell_ids_per_spike) != len(spike_times):
                continue

            st = spike_times[cell_ids_per_spike == cid]
            if len(st) == 0:
                continue

            # Interpolate position and speed at each spike time
            sp_pos   = np.interp(st, pos_ts, pos_1d, left=np.nan, right=np.nan)
            sp_speed = np.interp(st, pos_ts, speed,  left=0.0,    right=0.0)

            valid = ~np.isnan(sp_pos)
            if speed_thr > 0:
                valid &= (sp_speed >= speed_thr)

            # Restrict spikes to lap periods
            if laps_nd is not None:
                lap_list_filt = (
                    laps_nd.metadata.get("laps", [])
                    if direction == "both"
                    else [l for l in laps_nd.metadata.get("laps", [])
                          if str(l["direction"]) == direction]
                )
                in_lap = np.zeros(len(st), dtype=bool)
                for lap in lap_list_filt:
                    in_lap |= (st >= lap["t_start"]) & (st <= lap["t_end"])
                valid &= in_lap

            sp_pos = sp_pos[valid]
            counts, _ = np.histogram(sp_pos, bins=bins)

            with np.errstate(invalid="ignore", divide="ignore"):
                rate = np.where(occ_s >= min_occ, counts / occ_s, 0.0)

            if sigma > 0:
                rate = gaussian_filter1d(rate.astype(float), sigma=sigma)

            rate_maps[i] = rate.astype(np.float32)

        dir_label = {"1": "dir1", "2": "dir2", "both": "both"}.get(direction, direction)

        return {
            "tuning_curves": NeuroData(
                data_type     = "tuning_curves_population",
                array         = rate_maps,
                timestamps    = bin_centers.astype(np.float64),
                channel_names = [str(c) for c in cell_ids],
                metadata      = {
                    "cell_ids":     cell_ids.tolist(),
                    "pyr_ids":      spikes.metadata.get("pyr_ids", []),
                    "int_ids":      spikes.metadata.get("int_ids", []),
                    "n_bins":       n_bins,
                    "pos_min":      p_min,
                    "pos_max":      p_max,
                    "bin_centers":  bin_centers.tolist(),
                    "occupancy_s":  occ_s.tolist(),
                    "direction":    dir_label,
                    "bin_width_cm": float((p_max - p_min) / n_bins),
                },
            )
        }
