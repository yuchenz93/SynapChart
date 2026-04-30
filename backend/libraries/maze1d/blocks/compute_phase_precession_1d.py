"""Compute theta phase precession for every state in a NeuroData[states] object.

For each state the running direction is read directly from the state metadata,
so position normalisation (which end is the field entry) is automatic.
Phase is remapped to [0, 2π] before computing Pearson r so that the precession
arc (declining from ~270° to ~90° as position increases) yields a negative r
without wrap-around artefacts.

Output metadata layout::

    metadata["results_by_state"][state_name][cell_id_str]  →  list[field_dict]
    metadata["state_keys"]                                 →  list[str]
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


def _pearson_r(phases: np.ndarray, positions: np.ndarray):
    """Return (r, slope) via Pearson linear regression."""
    if len(phases) < 5:
        return np.nan, np.nan
    x = positions - positions.mean()
    y = phases    - phases.mean()
    ss_xx = float((x ** 2).sum())
    ss_yy = float((y ** 2).sum())
    ss_xy = float((x * y).sum())
    if ss_xx < 1e-12 or ss_yy < 1e-12:
        return np.nan, np.nan
    return float(ss_xy / np.sqrt(ss_xx * ss_yy)), float(ss_xy / ss_xx)


class ComputePhasePrecession1d(BlockBase):
    """Compute theta phase precession for every state — direction-aware."""

    block_type_id = "compute_phase_precession_1d"
    display_name  = "Phase Precession 1D"
    category      = "maze1d / Analysis"
    description   = (
        "For each state and cell, collects within-field spikes restricted to "
        "that state's time intervals, interpolates theta phase (remapped to "
        "[0, 2π]), computes direction-corrected normalised position, and returns "
        "the Pearson r.  Direction (1 = descending, 2 = ascending) is read from "
        "the state metadata automatically."
    )

    inputs = [
        PortDefinition("spike_data",   "NeuroData[multi_spike_times]",
                       "Multi-cell spike times (full session)."),
        PortDefinition("phase",        "NeuroData[raw_signal]",
                       "Instantaneous theta phase in radians from extract_phase."),
        PortDefinition("position",     "NeuroData[position]",
                       "Linearised 1-D position with timestamps (cm)."),
        PortDefinition("place_fields", "NeuroData[place_fields_1d]",
                       "Per-state place fields from detect_place_fields_1d."),
        PortDefinition("states",       "NeuroData[states]",
                       "Named states from define_maze_states."),
    ]
    outputs = [
        PortDefinition("phase_precession", "NeuroData[phase_precession_1d]",
                       "Per-state precession stats in metadata['results_by_state']."),
    ]
    parameters = [
        ParameterDefinition("min_spikes_per_field", "int",   10,
                            "Minimum within-field spike count to compute precession."),
        ParameterDefinition("speed_threshold",      "float",  5.0,
                            "Minimum speed (cm/s) to include a spike."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        spikes:    NeuroData = inputs["spike_data"]
        phase:     NeuroData = inputs["phase"]
        pos:       NeuroData = inputs["position"]
        pf:        NeuroData = inputs["place_fields"]
        states_nd: NeuroData = inputs["states"]

        min_spk   = int(parameters.get("min_spikes_per_field", 10))
        speed_thr = float(parameters.get("speed_threshold",     5.0))

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

        states_dict     = states_nd.metadata.get("states", {})
        state_keys      = states_nd.metadata.get("state_keys", list(states_dict.keys()))
        fields_by_state = pf.metadata.get("fields_by_state", {})
        cell_ids        = pf.metadata.get("cell_ids", [])
        pyr_ids         = pf.metadata.get("pyr_ids", [])
        int_ids         = pf.metadata.get("int_ids", [])

        results_by_state: dict[str, dict] = {}
        r_vals_by_state:  dict[str, list] = {}

        for sname in state_keys:
            state    = states_dict.get(sname, {})
            direction = state.get("direction", 2)
            intervals = state.get("intervals", [])

            fields_dict = fields_by_state.get(sname, {})

            results: dict[str, list] = {}
            r_vals:  list[float]     = []

            for cid in cell_ids:
                key          = str(cid)
                cell_fields  = fields_dict.get(key, [])
                if not cell_fields:
                    results[key] = []
                    continue

                if len(cell_ids_per_spike) == len(spike_times):
                    st_cell = spike_times[cell_ids_per_spike == int(cid)]
                else:
                    results[key] = []
                    continue

                # Restrict spikes to state intervals
                in_interval = np.zeros(len(st_cell), dtype=bool)
                for t0, t1 in intervals:
                    in_interval |= (st_cell >= t0) & (st_cell <= t1)

                cell_results: list[dict] = []
                for fld in cell_fields:
                    pos_start = fld["start_pos"]
                    pos_end   = fld["end_pos"]

                    sp_pos   = np.interp(st_cell, pos_ts, pos_1d,  left=np.nan, right=np.nan)
                    sp_speed = np.interp(st_cell, pos_ts, pos_speed, left=0.0,  right=0.0)

                    in_field = (
                        ~np.isnan(sp_pos)
                        & (sp_pos >= pos_start)
                        & (sp_pos <= pos_end)
                        & (sp_speed >= speed_thr)
                        & in_interval
                    )

                    if in_field.sum() < min_spk:
                        cell_results.append({
                            "r": np.nan, "slope": np.nan,
                            "n_spikes": int(in_field.sum()),
                            **{k: fld[k] for k in ("start_pos", "end_pos", "peak_pos")},
                        })
                        continue

                    field_spike_pos   = sp_pos[in_field]
                    field_spike_times = st_cell[in_field]

                    # Direction-corrected normalised position
                    field_width = pos_end - pos_start
                    if field_width <= 0:
                        cell_results.append({"r": np.nan, "slope": np.nan,
                                             "n_spikes": int(in_field.sum()),
                                             **{k: fld[k] for k in ("start_pos", "end_pos", "peak_pos")}})
                        continue

                    if direction == 1:
                        norm_pos = (pos_end - field_spike_pos) / field_width
                    else:
                        norm_pos = (field_spike_pos - pos_start) / field_width
                    norm_pos = np.clip(norm_pos, 0.0, 1.0)

                    # Phase in [0, 2π] to avoid wrap-around artefacts at ±π
                    sp_phase = np.interp(field_spike_times, phase_ts, phase_arr,
                                         left=phase_arr[0], right=phase_arr[-1])
                    sp_phase = sp_phase % (2 * np.pi)

                    r, slope = _pearson_r(sp_phase, norm_pos)

                    cell_results.append({
                        "r":         r,
                        "slope":     slope,
                        "n_spikes":  int(in_field.sum()),
                        "positions": norm_pos.tolist(),
                        "phases":    sp_phase.tolist(),
                        "start_pos": fld["start_pos"],
                        "end_pos":   fld["end_pos"],
                        "peak_pos":  fld["peak_pos"],
                        "peak_rate": fld["peak_rate"],
                        "direction": direction,
                    })
                    if not np.isnan(r):
                        r_vals.append(float(r))

                results[key] = cell_results

            results_by_state[sname] = results
            r_vals_by_state[sname]  = r_vals

        # Summary r array (mean across fields, first state)
        first_r = r_vals_by_state.get(state_keys[0], []) if state_keys else []
        r_arr   = np.array(first_r, dtype=np.float32) if first_r else np.array([], dtype=np.float32)

        return {
            "phase_precession": NeuroData(
                data_type = "phase_precession_1d",
                array     = r_arr,
                metadata  = {
                    "results_by_state": results_by_state,
                    "r_vals_by_state":  r_vals_by_state,
                    "state_keys":       state_keys,
                    "cell_ids":         cell_ids,
                    "pyr_ids":          pyr_ids,
                    "int_ids":          int_ids,
                },
            )
        }
