"""Detect waking rest frames during body-stationary moments with strong MUA.

Implements the two-substep logic from Yunzhen's ketamine project:
  Substep 1  CA_BodyStationary_epochs_v2   — low-pass velocity < threshold
  Substep 2  CA_AwakeRest_Frames_BSMUASTD  — find population-MUA burst frames

Algorithm
---------
1. Compute instantaneous speed from position.
2. Low-pass filter the speed trace (default cut-off 0.1 Hz) to suppress brief
   movement artefacts and get a ''body motion'' signal.
3. Find contiguous intervals where |lpvel| ≤ vel_threshold and that last at
   least min_stationary_s seconds → *body-stationary epochs*.
4. Within those epochs, bin all pyramidal-cell spikes into 1 ms bins and
   convolve with a Gaussian kernel (σ = smooth_sigma_s) to get smoothed MUA.
5. Compute the mean (μ) and std (σ) of smoothed MUA **during low-velocity
   moments** only (|speed| ≤ vel_threshold).
6. A frame starts every time smoothed MUA rises above μ and ends when it
   falls back below μ; only frames that *peak* above μ + mua_std_threshold × σ
   are kept.
7. Additional frame-quality criteria:
   • Frame duration ∈ [min_frame_s, max_frame_s]
   • Number of distinct active cells ≥ min_active_cells
   • All time samples inside the frame have speed ≤ vel_threshold

Output metadata layout::

    metadata["frames"]          → list[dict]   each with t_start, t_end,
                                                 n_active_cells, n_spikes,
                                                 mean_pos_cm (position at frame)
    metadata["n_frames"]        → int
    metadata["vel_threshold"]   → float (cm/s)
    metadata["mua_std"]         → float  (μ of smoothed MUA at low-vel)
    metadata["mua_mean"]        → float  (σ)
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class DetectWakingRestFrames(BlockBase):
    """Detect waking rest frames: body-stationary epochs with strong MUA bursts."""

    block_type_id = "detect_waking_rest_frames"
    display_name  = "Detect Waking Rest Frames"
    category      = "maze1d / Waking Rest"
    description   = (
        "Finds population-MUA burst frames that occur while the animal is "
        "stationary.  Step 1: low-pass-filter the speed trace and find "
        "body-stationary intervals.  Step 2: compute smoothed MUA from "
        "pyramidal-cell spikes, detect bursts that exceed mean + N×std during "
        "low-velocity moments, and apply duration / active-cell criteria."
    )

    inputs = [
        PortDefinition("spike_data", "NeuroData[multi_spike_times]",
                       "Multi-cell spike times with spike_cell_ids and pyr_ids in metadata."),
        PortDefinition("position",   "NeuroData[position]",
                       "Linearised 1-D position with timestamps (cm)."),
    ]
    outputs = [
        PortDefinition("rest_frames", "NeuroData[waking_rest_frames]",
                       "Frame time intervals and metadata in .metadata['frames']."),
    ]
    parameters = [
        ParameterDefinition("vel_threshold_cms",   "float", 5.0,
                            "Speed threshold (cm/s): samples with speed ≤ this are "
                            "counted as body-stationary."),
        ParameterDefinition("min_stationary_s",    "float", 0.5,
                            "Minimum duration (s) of a body-stationary epoch."),
        ParameterDefinition("lowpass_hz",          "float", 0.1,
                            "Low-pass filter cut-off (Hz) for the velocity trace "
                            "used to define body motion (FIR filter, order 30)."),
        ParameterDefinition("mua_std_threshold",   "float", 2.0,
                            "MUA frames must peak above mean + N×std of the "
                            "low-velocity MUA distribution."),
        ParameterDefinition("min_frame_s",         "float", 0.1,
                            "Minimum frame duration (s)."),
        ParameterDefinition("max_frame_s",         "float", 1.2,
                            "Maximum frame duration (s)."),
        ParameterDefinition("mua_bin_s",           "float", 0.001,
                            "MUA binning resolution (s). 0.001 = 1 ms."),
        ParameterDefinition("smooth_sigma_s",      "float", 0.015,
                            "Gaussian smoothing σ (s) for the MUA trace."),
        ParameterDefinition("min_active_cells",    "int",   5,
                            "Minimum number of distinct pyramidal cells that "
                            "must fire within a frame."),
        ParameterDefinition("pyr_only",            "bool",  True,
                            "If True, use only pyramidal cells for MUA computation."),
    ]

    # ------------------------------------------------------------------
    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        from scipy.signal import firwin, filtfilt
        from scipy.ndimage import gaussian_filter1d

        spikes:  NeuroData = inputs["spike_data"]
        pos_nd:  NeuroData = inputs["position"]

        vel_thr    = float(parameters.get("vel_threshold_cms",  5.0))
        min_stat   = float(parameters.get("min_stationary_s",   0.5))
        lp_hz      = float(parameters.get("lowpass_hz",         0.1))
        mua_std    = float(parameters.get("mua_std_threshold",   2.0))
        min_f      = float(parameters.get("min_frame_s",         0.1))
        max_f      = float(parameters.get("max_frame_s",         1.2))
        mua_bin    = float(parameters.get("mua_bin_s",           0.001))
        smooth_sig = float(parameters.get("smooth_sigma_s",      0.015))
        min_cells  = int(parameters.get("min_active_cells",      5))
        pyr_only   = bool(parameters.get("pyr_only",             True))

        # ── Position & velocity ───────────────────────────────────────────────
        pos_1d  = pos_nd.array.flatten().astype(np.float64)
        pos_ts  = pos_nd.timestamps
        pos_sr  = pos_nd.sampling_rate or 39.0
        if pos_ts is None:
            pos_ts = np.arange(len(pos_1d)) / pos_sr
        pos_sr = float(1.0 / np.median(np.diff(pos_ts)))

        raw_vel = np.abs(np.gradient(pos_1d, pos_ts))  # cm/s

        # Low-pass filter velocity (FIR, order 30)
        nyq    = pos_sr / 2.0
        cutoff = min(lp_hz / nyq, 0.99)
        b      = firwin(31, cutoff, window="hamming")
        lpvel  = filtfilt(b, [1.0], raw_vel)           # low-pass velocity

        # ── Body-stationary epochs (substep 1) ───────────────────────────────
        stat_mask = lpvel <= vel_thr                    # bool array
        stat_mask_raw = raw_vel <= vel_thr

        # Require minimum duration
        min_samp  = max(1, int(min_stat * pos_sr))
        padded    = np.concatenate([[False], stat_mask, [False]])
        d         = np.diff(padded.astype(np.int8))
        seg_starts = np.where(d ==  1)[0]
        seg_ends   = np.where(d == -1)[0]

        stat_intervals: list[tuple[float, float]] = []
        for s, e in zip(seg_starts, seg_ends):
            if (e - s) >= min_samp:
                stat_intervals.append((float(pos_ts[s]), float(pos_ts[e - 1])))

        if not stat_intervals:
            # Return empty frames
            return {
                "rest_frames": NeuroData(
                    data_type = "waking_rest_frames",
                    array     = np.zeros((0, 2), dtype=np.float64),
                    metadata  = {
                        "frames":         [],
                        "n_frames":       0,
                        "vel_threshold":  vel_thr,
                        "mua_mean":       0.0,
                        "mua_std_val":    0.0,
                    },
                )
            }

        # ── Spike selection ───────────────────────────────────────────────────
        spike_times        = spikes.array
        cell_ids_per_spike = np.asarray(spikes.metadata.get("spike_cell_ids", []))
        pyr_ids            = set(spikes.metadata.get("pyr_ids", []))

        if pyr_only and pyr_ids:
            keep = np.isin(cell_ids_per_spike.astype(int),
                           np.array(sorted(pyr_ids), dtype=int))
            spike_times        = spike_times[keep]
            cell_ids_per_spike = cell_ids_per_spike[keep]

        # ── MUA trace ────────────────────────────────────────────────────────
        t_start_all = float(pos_ts[0])
        t_end_all   = float(pos_ts[-1])
        bin_edges   = np.arange(t_start_all, t_end_all + mua_bin, mua_bin)
        bin_times   = (bin_edges[:-1] + bin_edges[1:]) / 2.0  # centre times

        # Histogram all spikes into 1 ms bins
        mua_raw, _ = np.histogram(spike_times, bins=bin_edges)
        mua_raw    = mua_raw.astype(np.float64)

        # Gaussian smooth
        sigma_bins = smooth_sig / mua_bin
        mua_smooth = gaussian_filter1d(mua_raw, sigma=sigma_bins)

        # Interpolate raw_vel onto MUA timescale
        mua_vel  = np.interp(bin_times, pos_ts, raw_vel)
        mua_lpvel = np.interp(bin_times, pos_ts, lpvel)

        # ── Baseline statistics on low-velocity samples (substep 2) ──────────
        lowv_mask   = mua_lpvel <= vel_thr
        if lowv_mask.sum() < 10:
            lowv_mask = mua_vel <= vel_thr          # fallback
        mu_mua  = float(np.mean(mua_smooth[lowv_mask]))
        sd_mua  = float(np.std(mua_smooth[lowv_mask]))
        hi_thr  = mu_mua + mua_std * sd_mua         # upper detection threshold
        lo_thr  = mu_mua                            # threshmin = 0

        # ── Frame detection ───────────────────────────────────────────────────
        # Find contiguous segments where mua_smooth > lo_thr
        above_lo  = mua_smooth > lo_thr
        padded2   = np.concatenate([[False], above_lo, [False]])
        d2        = np.diff(padded2.astype(np.int8))
        starts2   = np.where(d2 ==  1)[0]
        ends2     = np.where(d2 == -1)[0]

        frames: list[dict] = []
        for s, e in zip(starts2, ends2):
            # Frame time in seconds
            ft_start = float(bin_times[s])
            ft_end   = float(bin_times[e - 1])
            dur      = ft_end - ft_start

            # Duration criterion
            if dur < min_f or dur > max_f:
                continue

            # Must peak above hi_thr
            seg_mua = mua_smooth[s:e]
            if seg_mua.max() <= hi_thr:
                continue

            # All velocity samples in this frame must be ≤ threshold
            vel_in_frame = mua_vel[s:e]
            if np.any(vel_in_frame > vel_thr):
                continue

            # Active cell count
            in_frame = (spike_times >= ft_start) & (spike_times <= ft_end)
            active_cells = int(len(np.unique(cell_ids_per_spike[in_frame])))
            n_spikes     = int(in_frame.sum())
            if active_cells < min_cells:
                continue

            # Mean position during frame
            pos_in   = (pos_ts >= ft_start) & (pos_ts <= ft_end)
            mean_pos = float(np.mean(pos_1d[pos_in])) if pos_in.any() else np.nan

            frames.append({
                "t_start":       ft_start,
                "t_end":         ft_end,
                "n_active_cells": active_cells,
                "n_spikes":      n_spikes,
                "mean_pos_cm":   mean_pos,
            })

        arr = np.array([[f["t_start"], f["t_end"]] for f in frames],
                       dtype=np.float64) if frames else np.zeros((0, 2), dtype=np.float64)

        return {
            "rest_frames": NeuroData(
                data_type = "waking_rest_frames",
                array     = arr,
                metadata  = {
                    "frames":         frames,
                    "n_frames":       len(frames),
                    "vel_threshold":  vel_thr,
                    "mua_mean":       mu_mua,
                    "mua_std_val":    sd_mua,
                    "mua_hi_thr":     hi_thr,
                    "n_stat_epochs":  len(stat_intervals),
                },
            )
        }
