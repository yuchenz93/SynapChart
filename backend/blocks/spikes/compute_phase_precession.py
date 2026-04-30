"""Compute theta phase precession for each cell × place field.

For every (cell, field) pair:
  1. Collect spikes that occur while the animal is inside the field AND
     (optionally) within running laps of the selected direction.
  2. Assign each spike a theta phase (interpolated from the phase signal)
     and a normalised within-field position:
       - Direction 1 (descending, entry at high end):
           norm_pos = (field_end_pos − spike_pos) / field_width
       - Direction 2 (ascending, entry at low end) or 'both':
           norm_pos = (spike_pos − field_start_pos) / field_width
     In both cases norm_pos ∈ [0, 1] with 0 = field entry, 1 = field exit.
  3. Compute the Pearson linear correlation r between normalised position
     and theta phase (in radians).  Negative r indicates precession.

The ``phase`` input is expected to be instantaneous phase in radians (−π to π)
at the same temporal resolution as the LFP, as produced by extract_phase.
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


def _linear_correlation(phases: np.ndarray, positions: np.ndarray):
    """Return (r, slope) using standard Pearson linear regression.

    r     : Pearson correlation coefficient ∈ [−1, 1].
             Negative values indicate phase precession (phase decreases as
             the animal traverses the field, i.e. position increases).
    slope : linear regression slope in radians per unit normalised position.
    """
    n = len(phases)
    if n < 5:
        return np.nan, np.nan

    x = positions - positions.mean()
    y = phases    - phases.mean()

    ss_xx = float((x ** 2).sum())
    ss_yy = float((y ** 2).sum())
    ss_xy = float((x * y).sum())

    if ss_xx < 1e-12 or ss_yy < 1e-12:
        return np.nan, np.nan

    r     = ss_xy / np.sqrt(ss_xx * ss_yy)
    slope = ss_xy / ss_xx

    return float(r), float(slope)


class ComputePhasePrecession(BlockBase):
    """Compute θ-phase precession (r, slope) for every cell × place field."""

    block_type_id = "compute_phase_precession"
    display_name  = "Compute Phase Precession"
    category      = "Spikes"
    description   = (
        "For each cell and place field: collects within-field spikes (optionally "
        "restricted to direction-specific laps), interpolates theta phase and "
        "direction-corrected normalised position, and computes the Pearson linear "
        "correlation r and precession slope.  Negative r indicates phase precession."
    )

    inputs = [
        PortDefinition("spike_data",   "NeuroData[multi_spike_times]",
                       "Multi-cell spike times (maze epoch)."),
        PortDefinition("phase",        "NeuroData[raw_signal]",
                       "Instantaneous theta phase in radians (from extract_phase)."),
        PortDefinition("position",     "NeuroData[position]",
                       "Linearised 1-D position with timestamps."),
        PortDefinition("place_fields", "NeuroData[place_fields]",
                       "Per-cell place field boundaries (should match direction)."),
        PortDefinition("laps",         "NeuroData[laps]",
                       "Running laps from detect_run_laps.  When connected, only "
                       "within-field spikes that occur during a lap of the selected "
                       "direction are included.",
                       required=False),
    ]
    outputs = [
        PortDefinition("phase_precession", "NeuroData[phase_precession]",
                       "Per-cell × per-field r and slope values."),
    ]
    parameters = [
        ParameterDefinition("min_spikes_per_field", "int", 10,
                            "Minimum within-field spike count to compute precession."),
        ParameterDefinition("speed_threshold", "float", 5.0,
                            "Minimum instantaneous speed (cm/s) to include a spike."),
        ParameterDefinition("direction", "enum:both,1,2", "1",
                            "Running direction to include: '1'=descending (entry at high "
                            "end of field), '2'=ascending (entry at low end), 'both'=all. "
                            "Also controls normalised-position orientation: direction 1 "
                            "flips the axis so 0=entry=high end, 1=exit=low end."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        spikes: NeuroData = inputs["spike_data"]
        phase:  NeuroData = inputs["phase"]
        pos:    NeuroData = inputs["position"]
        pf:     NeuroData = inputs["place_fields"]
        laps_nd           = inputs.get("laps")

        min_spk   = int(parameters.get("min_spikes_per_field", 10))
        speed_thr = float(parameters.get("speed_threshold", 5.0))
        direction = str(parameters.get("direction", "1"))

        spike_times        = spikes.array
        cell_ids_per_spike = np.asarray(spikes.metadata.get("spike_cell_ids", []))

        phase_arr = phase.array.flatten()
        phase_ts  = phase.timestamps
        phase_sr  = phase.sampling_rate or 1250.0
        if phase_ts is None:
            phase_ts = np.arange(len(phase_arr)) / phase_sr

        pos_1d = pos.array.flatten()
        pos_ts = pos.timestamps
        pos_sr = pos.sampling_rate or 39.0
        if pos_ts is None:
            pos_ts = np.arange(len(pos_1d)) / pos_sr

        pos_speed = np.abs(np.gradient(pos_1d, pos_ts))

        # ── Build direction-specific lap mask for spike times ─────────────────
        # Pre-build an array of valid (t_start, t_end) intervals so the per-cell
        # loop is cheap.
        if laps_nd is not None and direction != "both":
            dir_int = int(direction)
            dir_laps = [
                (l["t_start"], l["t_end"])
                for l in laps_nd.metadata.get("laps", [])
                if l["direction"] == dir_int
            ]
        else:
            dir_laps = None   # no directional filtering

        fields_dict = pf.metadata.get("fields", {})
        cell_ids    = [int(c) for c in pf.metadata.get("cell_ids", [])]

        results: dict[str, list[dict]] = {}

        for cid in cell_ids:
            key = str(cid)
            cell_fields = fields_dict.get(key, [])
            if not cell_fields:
                results[key] = []
                continue

            if len(cell_ids_per_spike) == len(spike_times):
                st_cell = spike_times[cell_ids_per_spike == cid]
            else:
                results[key] = []
                continue

            # Direction lap mask for this cell's spike times
            if dir_laps is not None:
                lap_valid = np.zeros(len(st_cell), dtype=bool)
                for ls, le in dir_laps:
                    lap_valid |= (st_cell >= ls) & (st_cell <= le)
            else:
                lap_valid = np.ones(len(st_cell), dtype=bool)

            cell_results: list[dict] = []
            for fld in cell_fields:
                pos_start = fld["start_pos"]
                pos_end   = fld["end_pos"]

                sp_pos   = np.interp(st_cell, pos_ts, pos_1d, left=np.nan, right=np.nan)
                sp_speed = np.interp(st_cell, pos_ts, pos_speed, left=0.0,  right=0.0)

                in_field = (
                    ~np.isnan(sp_pos)
                    & (sp_pos >= pos_start)
                    & (sp_pos <= pos_end)
                    & (sp_speed >= speed_thr)
                    & lap_valid          # restrict to direction-matching laps
                )

                if in_field.sum() < min_spk:
                    cell_results.append({
                        "r": np.nan, "slope": np.nan,
                        "n_spikes": int(in_field.sum()),
                        **{k: fld[k] for k in ("start_pos", "end_pos", "peak_pos")},
                    })
                    continue

                field_spike_pos = sp_pos[in_field]
                field_spike_times = st_cell[in_field]

                # ── Direction-corrected normalised position ────────────────────
                # norm_pos = 0 at field entry, 1 at field exit.
                # Direction 1 (descending): animal enters at the HIGH end
                #   → norm_pos = (pos_end − spike_pos) / field_width
                # Direction 2 (ascending) or 'both': animal enters at the LOW end
                #   → norm_pos = (spike_pos − pos_start) / field_width
                field_width = pos_end - pos_start
                if field_width <= 0:
                    cell_results.append({
                        "r": np.nan, "slope": np.nan,
                        "n_spikes": int(in_field.sum()),
                        **{k: fld[k] for k in ("start_pos", "end_pos", "peak_pos")},
                    })
                    continue

                if direction == "1":
                    norm_pos = (pos_end - field_spike_pos) / field_width
                else:
                    norm_pos = (field_spike_pos - pos_start) / field_width

                norm_pos = np.clip(norm_pos, 0.0, 1.0)

                # Interpolate phase at spike times and convert to [0, 2π].
                # scipy.signal.hilbert returns phase in [−π, +π]; mapping to
                # [0, 2π] ensures theta precession (phase declining from ~270°
                # to ~90° as position increases) produces a negative Pearson r
                # without wrap-around artifacts at the ±π boundary.
                sp_phase = np.interp(field_spike_times, phase_ts, phase_arr,
                                     left=phase_arr[0], right=phase_arr[-1])
                sp_phase = sp_phase % (2 * np.pi)   # [−π, +π] → [0, 2π]

                r, slope = _linear_correlation(sp_phase, norm_pos)

                cell_results.append({
                    "r":           r,
                    "slope":       slope,
                    "n_spikes":    int(in_field.sum()),
                    "positions":   norm_pos.tolist(),
                    "phases":      sp_phase.tolist(),
                    "start_pos":   fld["start_pos"],
                    "end_pos":     fld["end_pos"],
                    "peak_pos":    fld["peak_pos"],
                    "peak_rate":   fld["peak_rate"],
                    "direction":   direction,
                })

            results[key] = cell_results

        # Summary r array (one value per cell, mean across fields)
        r_vals = []
        for cid in cell_ids:
            cell_r = [f["r"] for f in results.get(str(cid), []) if not np.isnan(f.get("r", np.nan))]
            r_vals.append(float(np.mean(cell_r)) if cell_r else np.nan)

        return {
            "phase_precession": NeuroData(
                data_type     = "phase_precession",
                array         = np.array(r_vals, dtype=np.float32),
                channel_names = [str(c) for c in cell_ids],
                metadata      = {
                    "results":   results,
                    "cell_ids":  [str(c) for c in cell_ids],
                    "pyr_ids":   pf.metadata.get("pyr_ids", []),
                    "int_ids":   pf.metadata.get("int_ids", []),
                    "direction": direction,
                },
            )
        }
