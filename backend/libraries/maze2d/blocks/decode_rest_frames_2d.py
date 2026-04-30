"""Bayesian 2D decode of waking-rest frames using 2D place maps as templates.

Mirrors CA_8Arm_AwakeRest_2DMazeDcd / BayePosDecode_2DMap_Lite_1frame.

Algorithm (per frame)
---------------------
1. Collect spike counts per cell in time bins of width tau, stepped by
   tau * (1 - overlap).  When overlap=0 bins are non-overlapping; when
   overlap=0.5 each bin starts halfway through the previous one.
2. Flatten each 2D rate map to the valid (visited) spatial bins.
3. Memoryless Bayesian decoder:
       log P(x|n) = Σ_i n_i · log(f_i(x)) − τ · Σ_i f_i(x)
   where f_i(x) is the firing rate of cell i at spatial bin x,
   n_i is the spike count in the time bin, and τ is the bin width.
4. Normalise per time bin → 2D posterior post (n_valid, n_tbins).
5. Soft transition accumulation:
       T[i, j] += Σ_t  post[i, t] · post[j, t+1]
   i.e. the expected number of i→j transitions, weighted by the full
   posterior rather than winner-take-all argmax.  Vectorised as:
       T += post[:, :-1] @ post[:, 1:].T
6. Argmax per time bin → decoded position sequence for quality measures.
7. Compute per-frame quality measures (max/mean/med jump in cm, spatial_range_cm).

Outputs
-------
``decoded_2d_rest`` NeuroData carrying:

    metadata["frames"]             → list[dict] per decoded frame
        frame_idx, t_start, t_end, t_bins,
        posterior   (n_valid × n_tbins, float32),
        argmax_valid (n_tbins,),
        max_jump_cm, mean_jump_cm, med_jump_cm,
        spatial_range_cm,
        n_active_cells, n_spikes
    metadata["transition_counts"]  → np.ndarray (n_valid, n_valid) float64  (soft)
    metadata["valid_flat"]         → np.ndarray (n_valid,)
    metadata["valid_ij"]           → np.ndarray (n_valid, 2) [xi, yi]
    metadata["bin_centers_x"]      → list[float] cm
    metadata["bin_centers_y"]      → list[float] cm
    metadata["bin_size_cm"]        → float
    metadata["n_x"], ["n_y"]       → int
    metadata["n_frames"]           → int (total detected)
    metadata["n_frames_decoded"]   → int (frames that passed min_n_bins)
    metadata["bin_size_sec"]       → float
    metadata["overlap"]            → float
    metadata["cell_ids"]           → list[int]
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class DecodeRestFrames2d(BlockBase):
    """2D Bayesian decode of waking-rest frames using 2D place maps."""

    block_type_id = "decode_rest_frames_2d"
    display_name  = "Decode Rest Frames 2D"
    category      = "maze2d / Analysis"
    description   = (
        "Runs a memoryless Bayesian decoder in 2D space for every detected "
        "waking-rest frame, using the 2D place maps as spatial templates.  "
        "Supports overlapping time bins (overlap parameter).  "
        "Outputs per-frame 2D posteriors, quality measures (max/med step "
        "distance, spatial range), and a directed transition matrix for "
        "neuronal distance computation."
    )

    inputs = [
        PortDefinition("rest_frames",  "NeuroData[rest_frames]",
                       "Waking-rest frame times from detect_waking_rest_frames."),
        PortDefinition("place_maps_2d", "NeuroData[place_maps_2d]",
                       "2D place maps — provides per-cell rate maps and the spatial grid."),
        PortDefinition("spike_data",   "NeuroData[multi_spike_times]",
                       "Full-session spike times with per-spike cell IDs."),
    ]
    outputs = [
        PortDefinition("decoded_2d_rest", "NeuroData[decoded_2d_rest]",
                       "Per-frame 2D posteriors, quality measures, and transition matrix."),
    ]
    parameters = [
        ParameterDefinition("bin_size_sec", "float", 0.02,
                            "Time bin width for decoding (s).  0.02 s matches "
                            "the MATLAB default (tbin=0.02)."),
        ParameterDefinition("overlap",      "float", 0.0,
                            "Fractional overlap between consecutive time bins "
                            "(0 = no overlap, 0.5 = half overlap).  "
                            "Step size = bin_size_sec * (1 - overlap)."),
        ParameterDefinition("min_n_bins",   "int",   5,
                            "Minimum number of time bins for a frame to be decoded."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        rf: NeuroData = inputs["rest_frames"]
        pm: NeuroData = inputs["place_maps_2d"]
        sp: NeuroData = inputs["spike_data"]

        tau      = float(parameters.get("bin_size_sec", 0.02))
        overlap  = float(parameters.get("overlap",      0.0))
        min_bins = int(parameters.get("min_n_bins",     5))

        overlap = max(0.0, min(overlap, 0.99))   # clamp to [0, 0.99)
        step    = tau * (1.0 - overlap)           # bin step size in seconds

        # ── Rest frames ───────────────────────────────────────────────────────
        frames_meta = rf.metadata.get("frames", [])

        # ── Place maps ────────────────────────────────────────────────────────
        rate_maps  = np.asarray(pm.metadata["maps"], dtype=np.float64)  # (n_cells, n_x, n_y)
        valid_mask = np.asarray(pm.metadata["valid_mask"], dtype=bool)  # (n_x, n_y)
        bcx        = np.asarray(pm.metadata["bin_centers_x"])           # (n_x,)
        bcy        = np.asarray(pm.metadata["bin_centers_y"])           # (n_y,)
        cell_ids   = list(pm.metadata["cell_ids"])
        n_x, n_y   = valid_mask.shape

        # Valid (visited) bin indices
        valid_flat = np.where(valid_mask.ravel())[0]   # (n_valid,)
        n_valid    = len(valid_flat)
        valid_ij   = np.stack(np.unravel_index(valid_flat, (n_x, n_y)), axis=1)
        # valid_ij[:, 0] = x-index, [:, 1] = y-index

        # Spatial positions of valid bins (for jump distance and spatial range)
        valid_x_cm = bcx[valid_ij[:, 0]]   # (n_valid,)
        valid_y_cm = bcy[valid_ij[:, 1]]   # (n_valid,)

        # ── Flatten rate maps to valid pixels ─────────────────────────────────
        n_cells   = rate_maps.shape[0]
        flat_maps = np.zeros((n_cells, n_valid), dtype=np.float64)
        for ci in range(n_cells):
            fm = rate_maps[ci].ravel()[valid_flat]
            # Add tiny noise to avoid log(0), mirroring MATLAB:
            #   flat_map = flat_map + nanmean(flat_map)/1e5
            mean_rate = float(fm.mean()) if fm.mean() > 0 else 1e-9
            fm = fm + mean_rate / 1e5
            flat_maps[ci] = fm

        flat_maps = np.maximum(flat_maps, 1e-10)
        log_flat  = np.log(flat_maps)        # (n_cells, n_valid)
        sum_flat  = flat_maps.sum(axis=0)    # (n_valid,) — Poisson normalisation

        # ── Spike data ────────────────────────────────────────────────────────
        spike_times        = sp.array
        cell_ids_per_spike = np.asarray(sp.metadata.get("spike_cell_ids", []))

        # Build per-cell spike time arrays — only for cells in the place map
        spike_dict: dict[int, np.ndarray] = {}
        for cid in cell_ids:
            mask = cell_ids_per_spike == cid
            spike_dict[cid] = spike_times[mask] if mask.any() else np.empty(0)

        # ── Soft transition matrix (accumulated over all frames) ─────────────
        # T[i, j] = Σ_{frames} Σ_t  post[i,t] · post[j,t+1]
        # (expected number of i→j transitions under the full posterior)
        T = np.zeros((n_valid, n_valid), dtype=np.float64)

        # ── Frame loop ────────────────────────────────────────────────────────
        decoded_frames: list[dict] = []
        n_decoded = 0

        for fidx, frame in enumerate(frames_meta):
            t0 = float(frame["t_start"])
            t1 = float(frame["t_end"])

            # ── Time bin edges (possibly overlapping) ──────────────────────
            # Each bin runs [start, start + tau); bins are spaced by `step`.
            bin_starts = np.arange(t0, t1 - tau + step * 0.5, step)
            # Drop any bin that would extend past t1
            bin_starts = bin_starts[bin_starts + tau <= t1 + 1e-9]
            n_tbins    = len(bin_starts)
            if n_tbins < min_bins:
                continue

            bin_ends  = bin_starts + tau
            bin_times = bin_starts + tau / 2.0   # bin centres (n_tbins,)

            # ── Spike count matrix (n_cells, n_tbins) ──────────────────────
            spike_mat      = np.zeros((n_cells, n_tbins), dtype=np.float64)
            n_spikes       = 0
            n_active_cells = 0

            for ci, cid in enumerate(cell_ids):
                st = spike_dict[cid]
                if len(st) == 0:
                    continue

                if overlap == 0.0:
                    # Non-overlapping: fast histogram
                    bin_edges = np.append(bin_starts, bin_ends[-1])
                    counts, _ = np.histogram(st, bins=bin_edges)
                else:
                    # Overlapping bins: vectorised membership test
                    # in_bin[spike, bin] = True if spike falls in that bin
                    in_bin = ((st[:, np.newaxis] >= bin_starts[np.newaxis, :]) &
                              (st[:, np.newaxis] <  bin_ends[np.newaxis, :]))
                    counts = in_bin.sum(axis=0)   # (n_tbins,)

                spike_mat[ci] = counts
                cell_spks = int(counts.sum())
                n_spikes += cell_spks
                if cell_spks > 0:
                    n_active_cells += 1

            # ── Bayesian decode: log P(x|n) ∝ Σ n_i log f_i(x) − τ Σ f_i(x)
            # log_flat: (n_cells, n_valid) → log_flat.T: (n_valid, n_cells)
            # spike_mat: (n_cells, n_tbins)
            # log_post: (n_valid, n_tbins)
            log_post  = log_flat.T @ spike_mat                        # (n_valid, n_tbins)
            log_post -= tau * sum_flat[:, np.newaxis]                 # Poisson penalty

            # Numerically stable normalise to probabilities
            log_post -= log_post.max(axis=0, keepdims=True)
            post      = np.exp(log_post)                              # (n_valid, n_tbins)
            col_sums  = post.sum(axis=0, keepdims=True)
            col_sums[col_sums < 1e-15] = 1.0
            post /= col_sums

            # ── Argmax per time bin → decoded position sequence ────────────
            # Used only for quality measures; NOT used for the transition matrix.
            argmax_valid = np.argmax(post, axis=0)                    # (n_tbins,)

            # ── Soft transition accumulation ────────────────────────────────
            # T[i,j] += Σ_t post[i,t] · post[j,t+1]
            # = post[:, :-1] @ post[:, 1:].T   shape (n_valid, n_valid)
            # Uses the full posterior at every time step, not just the argmax.
            if n_tbins > 1:
                T += post[:, :-1] @ post[:, 1:].T

            # ── Quality measures ────────────────────────────────────────────
            ax = valid_x_cm[argmax_valid]
            ay = valid_y_cm[argmax_valid]

            step_dists = np.sqrt(np.diff(ax) ** 2 + np.diff(ay) ** 2)
            max_jump  = float(np.max(step_dists))    if len(step_dists) > 0 else np.nan
            mean_jump = float(np.mean(step_dists))   if len(step_dists) > 0 else np.nan
            med_jump  = float(np.median(step_dists)) if len(step_dists) > 0 else np.nan

            # Spatial range: diagonal of the bounding box of visited argmax positions
            x_range = float(ax.max() - ax.min()) if len(ax) > 1 else 0.0
            y_range = float(ay.max() - ay.min()) if len(ay) > 1 else 0.0
            spatial_range_cm = float(np.sqrt(x_range ** 2 + y_range ** 2))

            decoded_frames.append({
                "frame_idx":        fidx,
                "t_start":          t0,
                "t_end":            t1,
                "t_bins":           bin_times.tolist(),
                "posterior":        post.astype(np.float32),   # (n_valid, n_tbins)
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
            "decoded_2d_rest": NeuroData(
                data_type = "decoded_2d_rest",
                array     = np.array([n_decoded], dtype=np.float64),
                metadata  = {
                    "frames":             decoded_frames,
                    "transition_counts":  T,
                    "valid_flat":         valid_flat,
                    "valid_ij":           valid_ij,
                    "bin_centers_x":      bcx.tolist(),
                    "bin_centers_y":      bcy.tolist(),
                    "bin_size_cm":        float(pm.metadata["bin_size_cm"]),
                    "n_x":                n_x,
                    "n_y":                n_y,
                    "n_frames":           len(frames_meta),
                    "n_frames_decoded":   n_decoded,
                    "bin_size_sec":       tau,
                    "overlap":            overlap,
                    "cell_ids":           cell_ids,
                },
            )
        }
