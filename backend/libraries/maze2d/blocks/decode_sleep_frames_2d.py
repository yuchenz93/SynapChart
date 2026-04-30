"""Bayesian 2D decode of sleep (pre-run or post-run) frames.

Mirrors CA_8Arm_AwakeRest_2DMazeDcd logic applied to sleep epochs.

Uses the same memoryless Bayesian decoder as decode_rest_frames_2d, but
operates on sleep frames (from detect_sleep_frames) rather than waking-rest
frames.  The epoch_label parameter selects which sleep epoch to decode:
  "pre"  — pre-run sleep only
  "post" — post-run sleep only
  "all"  — both epochs combined

Place maps from the MazeEpoch run are used as spatial templates (standard
approach: build receptive fields during running, decode sleep).

Output metadata layout::

    metadata["frames"]             → list[dict] per decoded frame
        frame_idx, t_start, t_end, epoch_label, t_bins,
        posterior   (n_valid × n_tbins, float32),
        argmax_valid (n_tbins,),
        max_jump_cm, mean_jump_cm, med_jump_cm,
        spatial_range_cm, n_active_cells, n_spikes
    metadata["transition_counts"]  → np.ndarray (n_valid, n_valid) float64 (soft)
    metadata["valid_flat"]         → np.ndarray (n_valid,)
    metadata["valid_ij"]           → np.ndarray (n_valid, 2) [xi, yi]
    metadata["bin_centers_x"]      → list[float] cm
    metadata["bin_centers_y"]      → list[float] cm
    metadata["bin_size_cm"]        → float
    metadata["n_x"], ["n_y"]       → int
    metadata["epoch_label"]        → str  ("pre", "post", or "all")
    metadata["n_frames"]           → int  (candidate frames after epoch filter)
    metadata["n_frames_decoded"]   → int  (frames that passed min_n_bins)
    metadata["bin_size_sec"]       → float
    metadata["overlap"]            → float
    metadata["cell_ids"]           → list[int]
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class DecodeSleepFrames2d(BlockBase):
    """2D Bayesian decode of pre- or post-run sleep frames."""

    block_type_id = "decode_sleep_frames_2d"
    display_name  = "Decode Sleep Frames 2D"
    category      = "maze2d / Analysis"
    description   = (
        "Runs a memoryless Bayesian decoder in 2D space for every detected "
        "sleep frame (pre-run or post-run), using the MazeEpoch 2D place maps "
        "as spatial templates.  Select which epoch to decode with the "
        "epoch_label parameter ('pre', 'post', or 'all').  "
        "Outputs per-frame 2D posteriors, quality measures, and a soft "
        "transition matrix for neuronal distance computation."
    )

    inputs = [
        PortDefinition("sleep_frames",  "NeuroData[sleep_frames]",
                       "Sleep frame times from detect_sleep_frames."),
        PortDefinition("place_maps_2d", "NeuroData[place_maps_2d]",
                       "2D place maps — provides per-cell rate maps and the spatial grid."),
        PortDefinition("spike_data",    "NeuroData[multi_spike_times]",
                       "Full-session spike times with per-spike cell IDs."),
    ]
    outputs = [
        PortDefinition("decoded_2d_sleep", "NeuroData[decoded_2d_sleep]",
                       "Per-frame 2D posteriors, quality measures, and transition matrix."),
    ]
    parameters = [
        ParameterDefinition("epoch_label",  "str",   "pre",
                            "Which sleep epoch to decode: 'pre', 'post', or 'all'."),
        ParameterDefinition("bin_size_sec", "float", 0.02,
                            "Time bin width for decoding (s)."),
        ParameterDefinition("overlap",      "float", 0.5,
                            "Fractional overlap between consecutive time bins "
                            "(0 = none, 0.5 = half overlap)."),
        ParameterDefinition("min_n_bins",   "int",   5,
                            "Minimum number of time bins for a frame to be decoded."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        sf: NeuroData = inputs["sleep_frames"]
        pm: NeuroData = inputs["place_maps_2d"]
        sp: NeuroData = inputs["spike_data"]

        epoch_sel = str(parameters.get("epoch_label",  "pre")).strip().lower()
        tau       = float(parameters.get("bin_size_sec", 0.02))
        overlap   = float(parameters.get("overlap",      0.5))
        min_bins  = int(parameters.get("min_n_bins",     5))

        overlap = max(0.0, min(overlap, 0.99))
        step    = tau * (1.0 - overlap)

        # ── Filter frames by epoch_label ──────────────────────────────────────
        all_frames = sf.metadata.get("frames", [])
        if epoch_sel == "all":
            frames_meta = all_frames
        else:
            frames_meta = [f for f in all_frames
                           if f.get("epoch_label", "").lower() == epoch_sel]

        # ── Place maps ────────────────────────────────────────────────────────
        rate_maps  = np.asarray(pm.metadata["maps"],        dtype=np.float64)  # (n_cells, n_x, n_y)
        valid_mask = np.asarray(pm.metadata["valid_mask"],  dtype=bool)         # (n_x, n_y)
        bcx        = np.asarray(pm.metadata["bin_centers_x"])
        bcy        = np.asarray(pm.metadata["bin_centers_y"])
        cell_ids   = list(pm.metadata["cell_ids"])
        n_x, n_y   = valid_mask.shape

        valid_flat = np.where(valid_mask.ravel())[0]
        n_valid    = len(valid_flat)
        valid_ij   = np.stack(np.unravel_index(valid_flat, (n_x, n_y)), axis=1)
        valid_x_cm = bcx[valid_ij[:, 0]]
        valid_y_cm = bcy[valid_ij[:, 1]]

        # ── Flatten rate maps to valid pixels ─────────────────────────────────
        n_cells   = rate_maps.shape[0]
        flat_maps = np.zeros((n_cells, n_valid), dtype=np.float64)
        for ci in range(n_cells):
            fm = rate_maps[ci].ravel()[valid_flat]
            mean_rate = float(fm.mean()) if fm.mean() > 0 else 1e-9
            fm = fm + mean_rate / 1e5
            flat_maps[ci] = fm

        flat_maps = np.maximum(flat_maps, 1e-10)
        log_flat  = np.log(flat_maps)
        sum_flat  = flat_maps.sum(axis=0)

        # ── Spike data ────────────────────────────────────────────────────────
        spike_times        = sp.array
        cell_ids_per_spike = np.asarray(sp.metadata.get("spike_cell_ids", []))

        spike_dict: dict[int, np.ndarray] = {}
        for cid in cell_ids:
            mask = cell_ids_per_spike == cid
            spike_dict[cid] = spike_times[mask] if mask.any() else np.empty(0)

        # ── Soft transition matrix ────────────────────────────────────────────
        T = np.zeros((n_valid, n_valid), dtype=np.float64)

        # ── Frame loop ────────────────────────────────────────────────────────
        decoded_frames: list[dict] = []
        n_decoded = 0

        for fidx, frame in enumerate(frames_meta):
            t0 = float(frame["t_start"])
            t1 = float(frame["t_end"])

            bin_starts = np.arange(t0, t1 - tau + step * 0.5, step)
            bin_starts = bin_starts[bin_starts + tau <= t1 + 1e-9]
            n_tbins    = len(bin_starts)
            if n_tbins < min_bins:
                continue

            bin_ends  = bin_starts + tau
            bin_times = bin_starts + tau / 2.0

            spike_mat      = np.zeros((n_cells, n_tbins), dtype=np.float64)
            n_spikes       = 0
            n_active_cells = 0

            for ci, cid in enumerate(cell_ids):
                st = spike_dict[cid]
                if len(st) == 0:
                    continue

                if overlap == 0.0:
                    bin_edges = np.append(bin_starts, bin_ends[-1])
                    counts, _ = np.histogram(st, bins=bin_edges)
                else:
                    in_bin = ((st[:, np.newaxis] >= bin_starts[np.newaxis, :]) &
                              (st[:, np.newaxis] <  bin_ends[np.newaxis, :]))
                    counts = in_bin.sum(axis=0)

                spike_mat[ci] = counts
                cell_spks = int(counts.sum())
                n_spikes += cell_spks
                if cell_spks > 0:
                    n_active_cells += 1

            # Bayesian decode
            log_post  = log_flat.T @ spike_mat
            log_post -= tau * sum_flat[:, np.newaxis]
            log_post -= log_post.max(axis=0, keepdims=True)
            post      = np.exp(log_post)
            col_sums  = post.sum(axis=0, keepdims=True)
            col_sums[col_sums < 1e-15] = 1.0
            post /= col_sums

            argmax_valid = np.argmax(post, axis=0)

            if n_tbins > 1:
                T += post[:, :-1] @ post[:, 1:].T

            ax = valid_x_cm[argmax_valid]
            ay = valid_y_cm[argmax_valid]
            step_dists = np.sqrt(np.diff(ax) ** 2 + np.diff(ay) ** 2)
            max_jump  = float(np.max(step_dists))    if len(step_dists) > 0 else np.nan
            mean_jump = float(np.mean(step_dists))   if len(step_dists) > 0 else np.nan
            med_jump  = float(np.median(step_dists)) if len(step_dists) > 0 else np.nan
            x_range = float(ax.max() - ax.min()) if len(ax) > 1 else 0.0
            y_range = float(ay.max() - ay.min()) if len(ay) > 1 else 0.0
            spatial_range_cm = float(np.sqrt(x_range ** 2 + y_range ** 2))

            decoded_frames.append({
                "frame_idx":        fidx,
                "t_start":          t0,
                "t_end":            t1,
                "epoch_label":      frame.get("epoch_label", epoch_sel),
                "t_bins":           bin_times.tolist(),
                "posterior":        post.astype(np.float32),
                "argmax_valid":     argmax_valid.tolist(),
                "max_jump_cm":      max_jump,
                "mean_jump_cm":     mean_jump,
                "med_jump_cm":      med_jump,
                "spatial_range_cm": spatial_range_cm,
                "n_active_cells":   n_active_cells,
                "n_spikes":         n_spikes,
            })
            n_decoded += 1

        return {
            "decoded_2d_sleep": NeuroData(
                data_type = "decoded_2d_sleep",
                array     = np.array([n_decoded], dtype=np.float64),
                metadata  = {
                    "frames":            decoded_frames,
                    "transition_counts": T,
                    "valid_flat":        valid_flat,
                    "valid_ij":          valid_ij,
                    "bin_centers_x":     bcx.tolist(),
                    "bin_centers_y":     bcy.tolist(),
                    "bin_size_cm":       float(pm.metadata["bin_size_cm"]),
                    "n_x":               n_x,
                    "n_y":               n_y,
                    "epoch_label":       epoch_sel,
                    "n_frames":          len(frames_meta),
                    "n_frames_decoded":  n_decoded,
                    "bin_size_sec":      tau,
                    "overlap":           overlap,
                    "cell_ids":          cell_ids,
                },
            )
        }
