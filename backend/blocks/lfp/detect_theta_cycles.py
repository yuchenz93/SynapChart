"""Detect individual theta cycles from an instantaneous-phase signal.

Cycle boundaries are defined at the **peaks** of the oscillation, identified as
ascending zero-crossings of the Hilbert instantaneous phase (phase goes from
just below 0 to just above 0, i.e. the signal is at its maximum amplitude).

Phase convention (scipy.signal.hilbert on the raw LFP):
  phase = 0   →  PEAK  of the LFP signal
  phase = ±π  →  TROUGH of the LFP signal

Peak-to-peak cycles therefore have their midpoint at phase ≈ ±π (the trough).
Within each cycle the phase runs monotonically from 0 → 2π (0°–360°), which
is the natural range for theta phase precession analysis.
Returns a (N_cycles × 2) array of [t_start, t_end] pairs.
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class DetectThetaCycles(BlockBase):
    """Detect theta cycle boundaries from an instantaneous-phase signal."""

    block_type_id = "detect_theta_cycles"
    display_name  = "Detect Theta Cycles"
    category      = "LFP / EEG"
    description   = (
        "Finds individual theta cycles by detecting the peaks of the LFP signal "
        "(ascending zero-crossings of instantaneous phase, i.e. phase crosses 0 "
        "from below). Returns peak-to-peak cycle boundaries so that the phase "
        "within each cycle runs from 0° to 360°, suitable for phase precession "
        "analysis. Returns (N_cycles × 2) [t_start, t_end] in NeuroData[theta_cycles]."
    )

    inputs = [
        PortDefinition("phase", "NeuroData[raw_signal]",
                       "Instantaneous phase in radians from extract_phase."),
    ]
    outputs = [
        PortDefinition("theta_cycles", "NeuroData[theta_cycles]",
                       "(N_cycles × 2) array of [t_start, t_end] in seconds."),
    ]
    parameters = [
        ParameterDefinition("min_cycle_dur", "float", 0.05,
                            "Minimum valid cycle duration in seconds (discard shorter)."),
        ParameterDefinition("max_cycle_dur", "float", 0.25,
                            "Maximum valid cycle duration in seconds (discard longer)."),
        ParameterDefinition("channel_index", "int", 0,
                            "Which channel to use if phase is multi-channel."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        phase: NeuroData = inputs["phase"]

        min_dur = float(parameters.get("min_cycle_dur", 0.05))
        max_dur = float(parameters.get("max_cycle_dur", 0.25))
        ch_idx  = int(parameters.get("channel_index",  0))

        arr = phase.array
        if arr.ndim == 2:
            arr = arr[:, ch_idx]
        elif arr.ndim > 2:
            raise ValueError(f"Expected 1-D or 2-D phase array, got {arr.shape}.")

        sr = phase.sampling_rate or 1250.0
        ts = phase.timestamps
        if ts is None:
            ts = np.arange(len(arr)) / sr

        # ── Peak detection via ascending zero-crossing ──────────────────────────
        # A peak occurs where the instantaneous phase crosses 0 from below:
        #   arr[i] < 0  and  arr[i+1] >= 0  (and the jump is small, not a wrap)
        # This is distinct from the trough wrap-around (arr[i] ≈ +π → arr[i+1] ≈ −π).
        dp    = np.diff(arr)
        cross = (arr[:-1] < 0) & (arr[1:] >= 0) & (dp < np.pi)
        cross_idx = np.where(cross)[0]

        if len(cross_idx) < 2:
            return {
                "theta_cycles": NeuroData(
                    data_type = "theta_cycles",
                    array     = np.empty((0, 2), dtype=np.float64),
                    metadata  = {"n_cycles": 0},
                )
            }

        # Sub-sample accurate peak times via linear interpolation.
        # At index i: arr[i] < 0 (just below 0), arr[i+1] >= 0 (just above 0).
        # Interpolate to find the instant when phase = 0.
        def _peak_time(i):
            t0, t1 = ts[i], ts[i + 1]
            p0     = arr[i]       # negative, near 0
            p1     = arr[i + 1]   # positive, near 0
            denom  = p1 - p0
            frac   = float(-p0 / denom) if abs(denom) > 1e-9 else 0.0
            return float(t0 + np.clip(frac, 0.0, 1.0) * (t1 - t0))

        peak_times = np.array([_peak_time(i) for i in cross_idx])

        # Build cycle boundaries: consecutive peak pairs
        starts = peak_times[:-1]
        ends   = peak_times[1:]
        durs   = ends - starts

        valid   = (durs >= min_dur) & (durs <= max_dur)
        cycles  = np.column_stack([starts[valid], ends[valid]])

        return {
            "theta_cycles": NeuroData(
                data_type = "theta_cycles",
                array     = cycles.astype(np.float64),
                metadata  = {
                    "n_cycles":     int(valid.sum()),
                    "mean_dur_ms":  float(np.mean(durs[valid]) * 1000) if valid.any() else 0.0,
                    "t_start":      float(cycles[0, 0]) if len(cycles) else 0.0,
                    "t_end":        float(cycles[-1, 1]) if len(cycles) else 0.0,
                },
            )
        }
