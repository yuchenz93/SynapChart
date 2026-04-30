"""Compute average theta sequences for every state in a NeuroData[states] object.

For each state:
  - Uses that state's decoded posterior (from decode_position_1d)
  - Restricts theta cycles to those falling within the state's time intervals
  - Shifts the position axis so that positive lag = ahead of the animal
    (for descending runs, direction=1, the axis is flipped so that future
     positions remain on the positive side)
  - Accumulates position-shifted posteriors aligned to each cycle centre

A merged "all" state is also emitted that pools cycles from all directions
with direction-correct position axes, giving a single grand-average sequence.

Output metadata layout::

    metadata["sequences"][state_name]  →  np.ndarray (n_time × n_pos_lags)
    metadata["sequences"]["all"]       →  np.ndarray — grand average (all directions)
    metadata["n_cycles_by_state"]      →  dict[str, int]
    metadata["state_keys"]             →  list[str]  (individual states + "all")
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class ComputeThetaSequences1d(BlockBase):
    """Average decoded posteriors across theta cycles — per state, direction-corrected."""

    block_type_id = "compute_theta_sequences_1d"
    display_name  = "Theta Sequences 1D"
    category      = "maze1d / Analysis"
    description   = (
        "For each state, accumulates and averages decoded posteriors across "
        "theta cycles that fall within that state's time intervals.  The "
        "position axis is direction-corrected: positive lag always means "
        "ahead of the animal (future position).  A merged 'all' state pools "
        "cycles from all directions after axis correction."
    )

    inputs = [
        PortDefinition("decoded",      "NeuroData[decoded_1d]",
                       "Per-state posteriors from decode_position_1d (fine bins, ~20 ms)."),
        PortDefinition("position",     "NeuroData[position]",
                       "Linearised 1-D position with timestamps."),
        PortDefinition("theta_cycles", "NeuroData[theta_cycles]",
                       "(N × 2) cycle boundaries from detect_theta_cycles."),
        PortDefinition("states",       "NeuroData[states]",
                       "Named states from define_maze_states."),
        PortDefinition("tuning_curves","NeuroData[tuning_curves_1d]",
                       "Provides position bin centres (optional).",
                       required=False),
    ]
    outputs = [
        PortDefinition("theta_sequences", "NeuroData[theta_sequence_1d]",
                       "Per-state + merged sequence matrices in metadata['sequences']."),
    ]
    parameters = [
        ParameterDefinition("n_time_per_cycle", "int",   36,
                            "Temporal bins across the full window (2 × half_window_ms)."),
        ParameterDefinition("half_window_ms",   "float", 180.0,
                            "Half-width of the time window around each cycle centre (ms)."),
        ParameterDefinition("min_speed",        "float", 5.0,
                            "Minimum running speed (cm/s) at cycle midpoint."),
        ParameterDefinition("n_pos_lags",       "int",   41,
                            "Width of look-ahead/behind axis in position bins (odd)."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        decoded:   NeuroData = inputs["decoded"]
        pos:       NeuroData = inputs["position"]
        cycles:    NeuroData = inputs["theta_cycles"]
        states_nd: NeuroData = inputs["states"]
        tc                   = inputs.get("tuning_curves")

        n_t        = int(parameters.get("n_time_per_cycle", 36))
        half_ms    = float(parameters.get("half_window_ms",   180.0))
        v_thr      = float(parameters.get("min_speed",         5.0))
        n_lag      = int(parameters.get("n_pos_lags",          41))
        if n_lag % 2 == 0:
            n_lag += 1

        half_s   = half_ms / 1000.0
        half_lag = n_lag // 2

        pos_1d = pos.array.flatten()
        pos_ts = pos.timestamps
        pos_sr = pos.sampling_rate or 39.0
        if pos_ts is None:
            pos_ts = np.arange(len(pos_1d)) / pos_sr
        pos_speed = np.abs(np.gradient(pos_1d, pos_ts))

        # Position bin centres
        if tc is not None and tc.metadata.get("bin_centers"):
            bin_centers = np.array(tc.metadata["bin_centers"])
        elif decoded.metadata.get("bin_centers"):
            bin_centers = np.array(decoded.metadata["bin_centers"])
        else:
            p_min = float(decoded.metadata.get("pos_min", pos_1d.min()))
            p_max = float(decoded.metadata.get("pos_max", pos_1d.max()))
            n_pos = decoded.array.shape[0]
            bin_centers = np.linspace(p_min, p_max, n_pos)
        n_pos_bins = len(bin_centers)

        bin_width_cm = float(decoded.metadata.get("bin_width_cm", 1.0))
        if tc is not None:
            bin_width_cm = float(tc.metadata.get("bin_width_cm", bin_width_cm))

        posteriors_all = decoded.metadata.get("posteriors", {})
        dec_times      = decoded.timestamps
        states_dict    = states_nd.metadata.get("states", {})
        state_keys     = states_nd.metadata.get("state_keys", list(states_dict.keys()))

        cycle_arr  = cycles.array        # (N, 2)
        t_grid_sec = np.linspace(-half_s, half_s, n_t)

        sequences_by_state: dict[str, np.ndarray] = {}
        n_cycles_by_state:  dict[str, int]         = {}

        # Grand-average accumulator (direction-corrected, all states merged)
        merged_accum = np.zeros((n_t, n_lag), dtype=np.float64)
        merged_count = 0

        for sname in state_keys:
            state     = states_dict.get(sname, {})
            intervals = state.get("intervals", [])
            posterior = posteriors_all.get(sname)

            # direction: 1 = descending (160→0), 2 = ascending (0→160)
            # pos_sign: +1 = positive lag → higher absolute position (ahead for ascending)
            #           -1 = positive lag → lower absolute position (ahead for descending)
            direction = state.get("direction", 2)
            pos_sign  = 1 if direction == 2 else -1

            if posterior is None or dec_times is None:
                sequences_by_state[sname] = np.zeros((n_t, n_lag), dtype=np.float32)
                n_cycles_by_state[sname]  = 0
                continue

            accumulated = np.zeros((n_t, n_lag), dtype=np.float64)
            count       = 0

            for cyc_start, cyc_end in cycle_arr:
                t_mid = (cyc_start + cyc_end) / 2.0

                # Speed filter
                v_mid = float(np.interp(t_mid, pos_ts, pos_speed))
                if v_mid < v_thr:
                    continue

                # Must fall within one of the state's intervals
                in_state = any(t0 <= t_mid <= t1 for t0, t1 in intervals)
                if not in_state:
                    continue

                # Extract decoded posteriors in window
                t_win_s = t_mid - half_s
                t_win_e = t_mid + half_s
                in_win  = (dec_times >= t_win_s) & (dec_times <= t_win_e)
                if in_win.sum() < 2:
                    continue

                cyc_post = posterior[:, in_win]   # (n_pos, k)
                t_rel    = dec_times[in_win] - t_mid

                # Interpolate each position bin onto fixed time grid
                norm_post = np.zeros((n_pos_bins, n_t), dtype=np.float64)
                for j in range(n_pos_bins):
                    norm_post[j] = np.interp(t_grid_sec, t_rel, cyc_post[j],
                                             left=0.0, right=0.0)

                # Shift position axis relative to animal.
                # lag_i - half_lag > 0 → ahead of animal (direction-corrected by pos_sign).
                t_abs   = t_mid + t_grid_sec
                shifted = np.zeros((n_t, n_lag), dtype=np.float64)
                for ti in range(n_t):
                    col     = norm_post[:, ti]
                    x_ref   = float(np.interp(t_abs[ti], pos_ts, pos_1d))
                    ref_bin = int(np.clip(np.searchsorted(bin_centers, x_ref),
                                         0, n_pos_bins - 1))
                    for lag_i in range(n_lag):
                        src = ref_bin + pos_sign * (lag_i - half_lag)
                        if 0 <= src < n_pos_bins:
                            shifted[ti, lag_i] = col[src]

                accumulated  += shifted
                count        += 1
                merged_accum += shifted
                merged_count += 1

            if count > 0:
                accumulated /= count

            sequences_by_state[sname] = accumulated.astype(np.float32)
            n_cycles_by_state[sname]  = count

        # Grand average across all states (direction-corrected)
        if merged_count > 0:
            merged_accum /= merged_count
        sequences_by_state["all"] = merged_accum.astype(np.float32)
        n_cycles_by_state["all"]  = merged_count

        output_keys   = list(state_keys) + ["all"]
        lag_positions = (np.arange(n_lag) - half_lag).astype(float)
        first_seq     = sequences_by_state[output_keys[0]] if output_keys \
                        else np.zeros((n_t, n_lag))

        return {
            "theta_sequences": NeuroData(
                data_type  = "theta_sequence_1d",
                array      = first_seq,
                timestamps = t_grid_sec,
                metadata   = {
                    "sequences":         sequences_by_state,
                    "n_cycles_by_state": n_cycles_by_state,
                    "state_keys":        output_keys,
                    "lag_positions":     lag_positions.tolist(),
                    "half_window_ms":    half_ms,
                    "min_speed":         v_thr,
                    "bin_width_cm":      bin_width_cm,
                    "n_time_per_cycle":  n_t,
                    "n_pos_lags":        n_lag,
                },
            )
        }
