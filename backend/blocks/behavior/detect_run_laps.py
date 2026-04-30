"""Detect directional running bouts (laps) from linearised position.

A lap is a continuous high-velocity run that satisfies three criteria:
  1. Instantaneous speed ≥ min_speed_cms cm/s for most of the run
  2. Total duration ≥ min_duration_s seconds
  3. Total path length ≥ min_distance_cm cm

Direction is determined from net displacement:
  direction = 1  → descending (high position → low position)
  direction = 2  → ascending  (low  position → high position)
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class DetectRunLaps(BlockBase):
    """Detect directional continuous running bouts (laps) from position."""

    block_type_id = "detect_run_laps"
    display_name  = "Detect Run Laps"
    category      = "Behavior"
    description   = (
        "Finds continuous running bouts in linearised position data. "
        "Each lap must exceed speed, duration, and total-distance thresholds. "
        "Direction 1 = descending position; Direction 2 = ascending position."
    )

    inputs = [
        PortDefinition(
            "position", "NeuroData[position]",
            "Linearised 1-D position with timestamps (cm, from load_crcns_session).",
        ),
    ]
    outputs = [
        PortDefinition(
            "laps", "NeuroData[laps]",
            "Array (n_laps × 3) = [t_start, t_end, direction]. "
            "Full lap metadata in .metadata['laps'].",
        ),
    ]
    parameters = [
        ParameterDefinition(
            "min_speed_cms", "float", 5.0,
            "Minimum instantaneous speed (cm/s) for a sample to be in a run.",
        ),
        ParameterDefinition(
            "min_duration_s", "float", 1.0,
            "Minimum lap duration (seconds).",
        ),
        ParameterDefinition(
            "min_distance_cm", "float", 30.0,
            "Minimum total path length (cm) during the run.",
        ),
        ParameterDefinition(
            "gap_fill_s", "float", 0.2,
            "Merge brief sub-threshold pauses shorter than this (seconds).",
        ),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        from scipy.ndimage import uniform_filter1d, binary_closing

        pos: NeuroData = inputs["position"]

        min_speed  = float(parameters.get("min_speed_cms",    5.0))
        min_dur    = float(parameters.get("min_duration_s",   1.0))
        min_dist   = float(parameters.get("min_distance_cm",  30.0))
        gap_fill_s = float(parameters.get("gap_fill_s",       0.2))

        pos_1d = pos.array.flatten()
        pos_ts = pos.timestamps
        pos_sr = pos.sampling_rate or 39.0
        if pos_ts is None:
            pos_ts = np.arange(len(pos_1d)) / pos_sr

        dt = float(np.median(np.diff(pos_ts)))

        # ── Smoothed speed ────────────────────────────────────────────────────
        # Gradient gives cm/s when position is in cm and timestamps in seconds
        speed_raw = np.abs(np.gradient(pos_1d, pos_ts))
        # Smooth over ~0.1 s to reduce tracking noise
        win = max(1, int(0.1 / dt))
        speed = uniform_filter1d(speed_raw, size=win)

        # ── Running mask with short-gap filling ───────────────────────────────
        is_running = speed >= min_speed
        gap_samp   = max(1, int(gap_fill_s / dt))
        is_running = binary_closing(is_running, structure=np.ones(gap_samp))

        # ── Segment boundaries ────────────────────────────────────────────────
        padded = np.concatenate([[False], is_running, [False]])
        diffs  = np.diff(padded.astype(np.int8))
        starts = np.where(diffs ==  1)[0]
        ends   = np.where(diffs == -1)[0]

        # ── Threshold each segment ────────────────────────────────────────────
        laps: list[dict] = []
        for s_idx, e_idx in zip(starts, ends):
            e_idx = min(e_idx, len(pos_ts) - 1)
            t_s = float(pos_ts[s_idx])
            t_e = float(pos_ts[e_idx])
            duration = t_e - t_s

            if duration < min_dur:
                continue

            seg_pos = pos_1d[s_idx : e_idx + 1]
            if len(seg_pos) < 2:
                continue

            path_len = float(np.sum(np.abs(np.diff(seg_pos))))
            if path_len < min_dist:
                continue

            net_disp = float(seg_pos[-1] - seg_pos[0])
            direction = 1 if net_disp < 0 else 2   # 1=descending, 2=ascending

            laps.append({
                "t_start":         t_s,
                "t_end":           t_e,
                "direction":       direction,
                "distance_cm":     path_len,
                "displacement_cm": abs(net_disp),
                "start_pos_cm":    float(seg_pos[0]),
                "end_pos_cm":      float(seg_pos[-1]),
                "duration_s":      duration,
            })

        arr = (np.array([[l["t_start"], l["t_end"], l["direction"]] for l in laps],
                         dtype=np.float64)
               if laps else np.zeros((0, 3), dtype=np.float64))

        n1 = sum(1 for l in laps if l["direction"] == 1)
        n2 = sum(1 for l in laps if l["direction"] == 2)

        return {
            "laps": NeuroData(
                data_type = "laps",
                array     = arr,
                metadata  = {
                    "laps":            laps,
                    "n_laps_total":    len(laps),
                    "n_laps_dir1":     n1,
                    "n_laps_dir2":     n2,
                    "min_speed_cms":   min_speed,
                    "min_duration_s":  min_dur,
                    "min_distance_cm": min_dist,
                },
            )
        }
