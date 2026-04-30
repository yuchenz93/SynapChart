"""Compute the average theta sequence (look-ahead / look-behind).

Algorithm (Pfeiffer & Foster 2013; Wikenheiser & Redish 2015):
  For each theta cycle during active running *in the selected direction*:
    1. Identify the cycle centre t_mid = (t_start + t_end) / 2.
       Because cycles are detected peak-to-peak, t_mid corresponds to the
       theta TROUGH — the phase where decoded posteriors reflect the animal's
       current location.
    2. Extract decoded posteriors in a symmetric window
       [t_mid − half_window_ms, t_mid + half_window_ms] (default ±180 ms
       spans ~3 theta cycles at 8 Hz).
    3. Interpolate each position-bin trace onto a fixed temporal grid of
       n_time_per_cycle evenly-spaced samples within the window.
    4. For each temporal bin, shift the position axis so that the animal's
       interpolated position at that time maps to the centre — transforming
       absolute position into relative position (negative = behind, positive
       = ahead).
    5. Accumulate and average across all valid cycles.

The output is a (n_time_per_cycle × n_pos_lags) matrix where rows correspond
to time relative to cycle centre (seconds, stored in .timestamps) and columns
correspond to relative position (in position-bin units, centred at zero).
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class ComputeThetaSequences(BlockBase):
    """Average decoded posteriors across theta cycles to reveal theta sequences."""

    block_type_id = "compute_theta_sequences"
    display_name  = "Compute Theta Sequences"
    category      = "Spikes"
    description   = (
        "Accumulates and averages decoded posteriors across theta cycles during "
        "running to reveal systematic look-ahead/look-behind (theta sequences). "
        "A symmetric ±half_window_ms window is extracted around each cycle "
        "centre (theta trough), giving ~3 cycles of context by default. "
        "When laps are connected, only cycles falling within laps of the selected "
        "direction are included — ensuring the decoder and accumulator use matched "
        "tuning curves and running epochs."
    )

    inputs = [
        PortDefinition("decoded",       "NeuroData[decoded]",
                       "Posterior probability matrix (n_pos_bins × n_time_bins)."),
        PortDefinition("position",      "NeuroData[position]",
                       "Linearised 1-D position with timestamps."),
        PortDefinition("theta_cycles",  "NeuroData[theta_cycles]",
                       "(N_cycles × 2) cycle boundaries from detect_theta_cycles."),
        PortDefinition("tuning_curves", "NeuroData[tuning_curves_population]",
                       "Population tuning curves (provides position bin centres). "
                       "Optional: if not connected, bins are estimated from position range.",
                       required=False),
        PortDefinition("laps",          "NeuroData[laps]",
                       "Running laps from detect_run_laps.  When connected, only "
                       "theta cycles whose midpoint falls inside a lap of the "
                       "selected direction are accumulated.",
                       required=False),
    ]
    outputs = [
        PortDefinition("theta_sequences", "NeuroData[theta_sequence]",
                       "(n_time_per_cycle × n_pos_lags) averaged sequence matrix. "
                       "timestamps = time relative to cycle centre in seconds."),
    ]
    parameters = [
        ParameterDefinition("n_time_per_cycle", "int",   36,
                            "Number of temporal bins across the full window "
                            "(2 × half_window_ms).  Default 36 gives ~10 ms per bin "
                            "at the default ±180 ms window."),
        ParameterDefinition("half_window_ms",   "float", 180.0,
                            "Half-width of the time window centred at each cycle "
                            "trough (ms).  Default 180 ms spans ~3 theta cycles at "
                            "8 Hz and is the recommended value for visualising "
                            "look-ahead / look-behind sequences."),
        ParameterDefinition("min_speed",        "float",  5.0,
                            "Minimum running speed (cm/s) at cycle midpoint to include cycle."),
        ParameterDefinition("n_pos_lags",       "int",   41,
                            "Width of the look-ahead/behind axis in position bins (odd number)."),
        ParameterDefinition("direction",        "enum:both,1,2", "1",
                            "Running direction to include: '1'=descending, '2'=ascending, "
                            "'both'=all.  Only used when laps are connected."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        decoded:  NeuroData = inputs["decoded"]
        pos:      NeuroData = inputs["position"]
        cycles:   NeuroData = inputs["theta_cycles"]
        tc                  = inputs.get("tuning_curves")
        laps_nd             = inputs.get("laps")

        n_t       = int(parameters.get("n_time_per_cycle", 36))
        half_win_ms = float(parameters.get("half_window_ms",  180.0))
        v_thr     = float(parameters.get("min_speed",       5.0))
        n_lag     = int(parameters.get("n_pos_lags",        41))
        direction = str(parameters.get("direction",         "1"))
        if n_lag % 2 == 0:
            n_lag += 1   # keep odd so centre bin is exactly zero

        half_win_s = half_win_ms / 1000.0

        posterior   = decoded.array           # (n_pos_bins, n_time_bins)
        dec_times   = decoded.timestamps      # (n_time_bins,)
        n_pos_bins  = posterior.shape[0]

        pos_1d = pos.array.flatten()
        pos_ts = pos.timestamps
        pos_sr = pos.sampling_rate or 39.0
        if pos_ts is None:
            pos_ts = np.arange(len(pos_1d)) / pos_sr

        # Position bin centres from tuning curves or estimated
        if tc is not None and tc.timestamps is not None:
            bin_centers = np.asarray(tc.timestamps)
        else:
            p_min = float(decoded.metadata.get("pos_min", pos_1d.min()))
            p_max = float(decoded.metadata.get("pos_max", pos_1d.max()))
            bin_centers = np.linspace(p_min, p_max, n_pos_bins)

        pos_speed = np.abs(np.gradient(pos_1d, pos_ts))

        # ── Build direction-specific lap intervals ────────────────────────────
        dir_lap_intervals: list[tuple[float, float]] | None = None
        if laps_nd is not None and direction != "both":
            dir_int = int(direction)
            dir_lap_intervals = [
                (l["t_start"], l["t_end"])
                for l in laps_nd.metadata.get("laps", [])
                if l["direction"] == dir_int
            ]

        cycle_arr = cycles.array    # (N, 2)
        half_lag  = n_lag // 2

        # Fixed temporal grid: seconds relative to cycle centre (negative = before)
        t_grid_sec = np.linspace(-half_win_s, half_win_s, n_t)

        accumulated = np.zeros((n_t, n_lag), dtype=np.float64)
        count       = 0

        for cyc_start, cyc_end in cycle_arr:
            if dec_times is None:
                continue

            # Cycle centre = temporal midpoint = theta trough (peak-to-peak cycles)
            t_mid = (cyc_start + cyc_end) / 2.0

            # Speed at cycle midpoint
            v_mid = float(np.interp(t_mid, pos_ts, pos_speed))
            if v_mid < v_thr:
                continue

            # Direction filter
            if dir_lap_intervals is not None:
                if not any(ls <= t_mid <= le for ls, le in dir_lap_intervals):
                    continue

            # Extract decoded posteriors within ±half_win around centre
            t_win_start = t_mid - half_win_s
            t_win_end   = t_mid + half_win_s
            in_window   = (dec_times >= t_win_start) & (dec_times <= t_win_end)
            if in_window.sum() < 2:
                continue

            cyc_post = posterior[:, in_window]          # (n_pos, k)
            t_rel    = dec_times[in_window] - t_mid     # relative time in seconds

            # Interpolate each position bin onto fixed time grid
            # Values outside the data range are set to 0 (not extrapolated)
            norm_post = np.zeros((n_pos_bins, n_t), dtype=np.float64)
            for j in range(n_pos_bins):
                norm_post[j, :] = np.interp(
                    t_grid_sec, t_rel, cyc_post[j, :], left=0.0, right=0.0
                )

            # Absolute times for each grid point (for position interpolation)
            t_abs = t_mid + t_grid_sec   # (n_t,)

            # Shift position axis: animal's actual position at each temporal bin
            shifted = np.zeros((n_t, n_lag), dtype=np.float64)
            for ti in range(n_t):
                col      = norm_post[:, ti]
                x_ref    = float(np.interp(t_abs[ti], pos_ts, pos_1d))
                ref_bin  = int(np.clip(
                    np.searchsorted(bin_centers, x_ref), 0, n_pos_bins - 1
                ))
                for lag_i in range(n_lag):
                    src_bin = ref_bin + (lag_i - half_lag)
                    if 0 <= src_bin < n_pos_bins:
                        shifted[ti, lag_i] = col[src_bin]

            accumulated += shifted
            count += 1

        if count > 0:
            accumulated /= count

        lag_positions = (np.arange(n_lag) - half_lag).astype(float)
        bin_width_cm  = float(tc.metadata.get("bin_width_cm", 1.0)) if tc is not None else 1.0

        return {
            "theta_sequences": NeuroData(
                data_type  = "theta_sequence",
                array      = accumulated.astype(np.float32),
                # timestamps in seconds relative to cycle centre:
                # negative = before trough, 0 = trough, positive = after trough
                timestamps = t_grid_sec,
                metadata   = {
                    "n_cycles":           count,
                    "n_time_per_cycle":   n_t,
                    "n_pos_lags":         n_lag,
                    "lag_positions":      lag_positions.tolist(),
                    "half_window_ms":     half_win_ms,
                    "min_speed":          v_thr,
                    "direction":          direction,
                    "bin_width_cm":       bin_width_cm,
                },
            )
        }
