"""Detect MUA burst frames during sleep (pre-run and post-run epochs).

Implements the logic from CA_Sleep_Frames_Usm_MUASTD / framesexceedSDvlimthrlim_yc
for CRCNS hc-11 data.  Because the CRCNS dataset does not provide sleep-box
position, the velocity criterion is not applied; during sleep the animal is
confined to a rest box and is inherently stationary.

Algorithm (applied separately to PREEpoch and POSTEpoch)
---------------------------------------------------------
1. Select pyramidal-cell spikes within the epoch time window.
2. Bin spike counts into 1 ms bins and convolve with a Gaussian kernel
   (σ = smooth_sigma_s) to obtain smoothed MUA.
3. Compute the mean (μ) and std (σ) of the smoothed MUA over the entire epoch.
4. A frame starts when smoothed MUA rises above μ (threshmin = 0) and ends
   when it falls back to μ; only frames that *peak* above μ + mua_std_threshold × σ
   are kept.
5. Quality criteria: duration ∈ [min_frame_s, max_frame_s] and at least
   min_active_cells distinct pyramidal cells fire within the frame.

Each frame is tagged with its epoch label ("pre" or "post").

Output metadata layout::

    metadata["frames"]           → list[dict]  each with
                                     t_start, t_end, epoch_label,
                                     n_active_cells, n_spikes
    metadata["n_frames"]         → int  (total across both epochs)
    metadata["n_frames_pre"]     → int
    metadata["n_frames_post"]    → int
    metadata["mua_mean_pre"]     → float
    metadata["mua_std_pre"]      → float
    metadata["mua_mean_post"]    → float
    metadata["mua_std_post"]     → float
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class DetectSleepFrames(BlockBase):
    """Detect MUA burst frames in pre-run and post-run sleep epochs."""

    block_type_id = "detect_sleep_frames"
    display_name  = "Detect Sleep Frames"
    category      = "maze1d / Sleep"
    description   = (
        "Finds population-MUA burst frames during PREEpoch and POSTEpoch "
        "(pre-run and post-run sleep).  Uses the same smoothed-MUA burst "
        "detection as detect_waking_rest_frames but without a velocity filter "
        "(CRCNS sleep sessions have no position data; the animal is stationary "
        "in a rest box throughout).  Each frame is tagged as 'pre' or 'post'."
    )

    inputs = [
        PortDefinition("spike_data",   "NeuroData[multi_spike_times]",
                       "Multi-cell spike times with pyr_ids in metadata."),
        PortDefinition("epochs_info",  "NeuroData[epochs]",
                       "Epoch boundaries from load_crcns_session "
                       "(must contain PREEpoch and POSTEpoch keys)."),
    ]
    outputs = [
        PortDefinition("sleep_frames", "NeuroData[sleep_frames]",
                       "Frame time intervals tagged with epoch label."),
    ]
    parameters = [
        ParameterDefinition("mua_std_threshold",   "float", 2.0,
                            "MUA frames must peak above mean + N×std."),
        ParameterDefinition("min_frame_s",         "float", 0.1,
                            "Minimum frame duration (s)."),
        ParameterDefinition("max_frame_s",         "float", 1.2,
                            "Maximum frame duration (s)."),
        ParameterDefinition("mua_bin_s",           "float", 0.001,
                            "MUA binning resolution (s). 0.001 = 1 ms."),
        ParameterDefinition("smooth_sigma_s",      "float", 0.015,
                            "Gaussian smoothing σ (s) for the MUA trace."),
        ParameterDefinition("min_active_cells",    "int",   5,
                            "Minimum distinct pyramidal cells that must fire "
                            "within a frame."),
        ParameterDefinition("pyr_only",            "bool",  True,
                            "If True, use only pyramidal cells for MUA."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        from scipy.ndimage import gaussian_filter1d

        spikes:     NeuroData = inputs["spike_data"]
        epochs_nd:  NeuroData = inputs["epochs_info"]

        mua_std    = float(parameters.get("mua_std_threshold",  2.0))
        min_f      = float(parameters.get("min_frame_s",         0.1))
        max_f      = float(parameters.get("max_frame_s",         1.2))
        mua_bin    = float(parameters.get("mua_bin_s",           0.001))
        smooth_sig = float(parameters.get("smooth_sigma_s",      0.015))
        min_cells  = int(parameters.get("min_active_cells",      5))
        pyr_only   = bool(parameters.get("pyr_only",             True))

        # ── Spike selection ───────────────────────────────────────────────────
        spike_times        = spikes.array
        cell_ids_per_spike = np.asarray(spikes.metadata.get("spike_cell_ids", []))
        pyr_ids            = set(spikes.metadata.get("pyr_ids", []))

        if pyr_only and pyr_ids:
            keep = np.isin(cell_ids_per_spike.astype(int),
                           np.array(sorted(pyr_ids), dtype=int))
            spike_times        = spike_times[keep]
            cell_ids_per_spike = cell_ids_per_spike[keep]

        # ── Epoch boundaries ──────────────────────────────────────────────────
        ep = epochs_nd.metadata

        def _epoch_interval(key: str):
            v = ep.get(key)
            if v is None:
                return None
            arr = np.asarray(v, dtype=np.float64).flatten()
            if len(arr) >= 2:
                return float(arr[0]), float(arr[-1])
            return None

        pre_interval  = _epoch_interval("PREEpoch")
        post_interval = _epoch_interval("POSTEpoch")

        if pre_interval is None and post_interval is None:
            raise ValueError(
                "detect_sleep_frames: epochs_info contains neither "
                "PREEpoch nor POSTEpoch."
            )

        # ── Per-epoch frame detection ─────────────────────────────────────────
        all_frames: list[dict] = []
        epoch_stats: dict[str, dict] = {}

        sigma_bins = smooth_sig / mua_bin   # σ in MUA bins

        for epoch_label, interval in [("pre", pre_interval),
                                      ("post", post_interval)]:
            if interval is None:
                epoch_stats[epoch_label] = {"mean": 0.0, "std": 0.0, "n": 0}
                continue

            t0_ep, t1_ep = interval

            # MUA bins for this epoch
            bin_edges  = np.arange(t0_ep, t1_ep + mua_bin, mua_bin)
            bin_times  = (bin_edges[:-1] + bin_edges[1:]) / 2.0

            # Select spikes in epoch
            in_epoch = (spike_times >= t0_ep) & (spike_times <= t1_ep)
            st_ep    = spike_times[in_epoch]
            ci_ep    = cell_ids_per_spike[in_epoch]

            # Histogram spikes into 1 ms bins
            mua_raw, _ = np.histogram(st_ep, bins=bin_edges)
            mua_raw    = mua_raw.astype(np.float64)

            # Smooth
            mua_smooth = gaussian_filter1d(mua_raw, sigma=sigma_bins)

            # Baseline: mean and std over entire epoch (no velocity mask in sleep)
            mu_mua = float(np.mean(mua_smooth))
            sd_mua = float(np.std(mua_smooth))
            hi_thr = mu_mua + mua_std * sd_mua
            lo_thr = mu_mua   # threshmin = 0

            epoch_stats[epoch_label] = {
                "mean": mu_mua, "std": sd_mua, "n": 0
            }

            if sd_mua < 1e-12:
                # Flat MUA — no frames possible
                continue

            # ── Frame detection ───────────────────────────────────────────────
            above_lo = mua_smooth > lo_thr
            padded   = np.concatenate([[False], above_lo, [False]])
            d        = np.diff(padded.astype(np.int8))
            starts   = np.where(d ==  1)[0]
            ends     = np.where(d == -1)[0]

            for s, e in zip(starts, ends):
                ft_start = float(bin_times[s])
                ft_end   = float(bin_times[e - 1])
                dur      = ft_end - ft_start

                if dur < min_f or dur > max_f:
                    continue

                seg = mua_smooth[s:e]
                if seg.max() <= hi_thr:
                    continue

                # Active cell count
                in_frame     = (st_ep >= ft_start) & (st_ep <= ft_end)
                active_cells = int(len(np.unique(ci_ep[in_frame])))
                n_spikes     = int(in_frame.sum())
                if active_cells < min_cells:
                    continue

                all_frames.append({
                    "t_start":        ft_start,
                    "t_end":          ft_end,
                    "epoch_label":    epoch_label,
                    "n_active_cells": active_cells,
                    "n_spikes":       n_spikes,
                })

            epoch_stats[epoch_label]["n"] = sum(
                1 for f in all_frames if f["epoch_label"] == epoch_label
            )

        n_pre  = sum(1 for f in all_frames if f["epoch_label"] == "pre")
        n_post = sum(1 for f in all_frames if f["epoch_label"] == "post")

        arr = np.array(
            [[f["t_start"], f["t_end"]] for f in all_frames],
            dtype=np.float64,
        ) if all_frames else np.zeros((0, 2), dtype=np.float64)

        return {
            "sleep_frames": NeuroData(
                data_type = "sleep_frames",
                array     = arr,
                metadata  = {
                    "frames":        all_frames,
                    "n_frames":      len(all_frames),
                    "n_frames_pre":  n_pre,
                    "n_frames_post": n_post,
                    "mua_mean_pre":  epoch_stats.get("pre",  {}).get("mean", 0.0),
                    "mua_std_pre":   epoch_stats.get("pre",  {}).get("std",  0.0),
                    "mua_mean_post": epoch_stats.get("post", {}).get("mean", 0.0),
                    "mua_std_post":  epoch_stats.get("post", {}).get("std",  0.0),
                    "mua_std_threshold": mua_std,
                },
            )
        }
