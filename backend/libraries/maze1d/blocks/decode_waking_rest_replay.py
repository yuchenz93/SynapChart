"""Bayesian decode waking-rest frames and assess replay significance.

For each detected rest frame the block:
  1. Slices the pre-computed state posteriors (from decode_position_1d) to the
     frame's time window.
  2. Computes the *absolute* quality measures:
       • weighted correlation (Farooq 2019, Pdf2DCorr)
       • maximum position jump between successive decoded bins (cm)
       • normalised max jump  = max_jump_cm / track_length_cm
  3. Shuffles the time columns of the posterior 100 times and records the
     shuffle distribution for each measure.
  4. Flags a frame×direction as **significant** if the observed weighted
     correlation falls below the 2.5th or above the 97.5th percentile of the
     shuffle distribution (i.e. is more structured than 95 % of shuffles).
  5. Records the best direction (highest |wc|) for every frame.

Output metadata layout::

    metadata["results"]           → list[dict] – one entry per (frame × dir)
        each dict has:
            frame_idx, t_start, t_end, state_key, direction,
            wc          (weighted correlation),
            max_jump_cm (absolute max jump in cm),
            norm_max_jump (max_jump_cm / track_length_cm),
            wc_pct      (percentile of wc among shuffles, 0–100),
            is_sig      (bool: wc_pct < 2.5 or > 97.5),
            n_active_cells, n_spikes, mean_pos_cm
    metadata["n_frames"]          → int
    metadata["n_sig_frames"]      → int  (≥1 significant direction)
    metadata["sig_ratio"]         → float  (n_sig / n_total_frames)
    metadata["track_length_cm"]   → float
    metadata["state_keys"]        → list[str]
    metadata["bin_centers"]       → list[float]
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


# ---------------------------------------------------------------------------
# Pure-Python helpers (translated from MATLAB originals)
# ---------------------------------------------------------------------------

def _weighted_correlation(pdf: np.ndarray) -> float:
    """Weighted correlation between time and position (Farooq 2019).

    pdf: (n_pos, n_time) float array, columns normalised to sum 1.
    Returns r ∈ [-1, 1].
    """
    np_bins, nt = pdf.shape
    if nt < 2 or np_bins < 2:
        return np.nan

    lpos = np.arange(1, np_bins + 1, dtype=np.float64)[:, None]  # (np, 1)
    lt   = np.arange(1, nt + 1,      dtype=np.float64)[None, :]  # (1, nt)

    total = pdf.sum()
    if total == 0:
        return np.nan

    mpos = (pdf * lpos).sum() / total
    mt   = (pdf * lt).sum()   / total

    dp = lpos - mpos
    dt = lt   - mt

    cov_pt  = (pdf * dp * dt).sum() / total
    var_p   = (pdf * dp * dp).sum() / total
    var_t   = (pdf * dt * dt).sum() / total

    denom = np.sqrt(var_p) * np.sqrt(var_t)
    if denom < 1e-15:
        return np.nan
    return float(cov_pt / denom)


def _max_jump(pdf: np.ndarray, bin_centers: np.ndarray) -> float:
    """Maximum absolute position jump between successive decoded time bins (cm).

    pdf: (n_pos, n_time).  Uniform-prob columns (no info) are excluded.
    bin_centers: position bin centres in cm, length n_pos.
    """
    stdp  = pdf.std(axis=0)
    valid = stdp > 1e-12
    if valid.sum() < 2:
        return np.nan

    pdf_v   = pdf[:, valid]
    max_idx = pdf_v.argmax(axis=0)               # argmax along position axis
    decoded = bin_centers[max_idx]               # cm
    jumps   = np.abs(np.diff(decoded))
    return float(jumps.max())


# ---------------------------------------------------------------------------
# Block
# ---------------------------------------------------------------------------

class DecodeWakingRestReplay(BlockBase):
    """Assess replay significance for each waking-rest frame via shuffled decoding."""

    block_type_id = "decode_waking_rest_replay"
    display_name  = "Decode Waking Rest Replay"
    category      = "maze1d / Waking Rest"
    description   = (
        "Slices the session-level Bayesian posteriors (decode_position_1d output) "
        "to each detected rest frame, computes weighted correlation and max-jump "
        "quality measures, runs 100 time-bin shuffles, and flags frames as "
        "significant if the observed wc falls outside the 2.5–97.5 % shuffle range."
    )

    inputs = [
        PortDefinition("decoded",     "NeuroData[decoded_1d]",
                       "Per-state posteriors from decode_position_1d."),
        PortDefinition("rest_frames", "NeuroData[waking_rest_frames]",
                       "Rest frame intervals from detect_waking_rest_frames."),
    ]
    outputs = [
        PortDefinition("replay_results", "NeuroData[replay_results]",
                       "Per-frame quality metrics and significance flags."),
    ]
    parameters = [
        ParameterDefinition("n_shuffles",       "int",   500,
                            "Number of time-column shuffles for significance testing."),
        ParameterDefinition("track_length_cm",  "float", 160.0,
                            "Track length (cm) used for jump normalisation."),
        ParameterDefinition("min_pos_bins",     "int",   5,
                            "Minimum decodable time bins required to assess a frame. "
                            "Frames with fewer bins are skipped."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        decoded:     NeuroData = inputs["decoded"]
        frames_nd:   NeuroData = inputs["rest_frames"]

        n_shuf    = int(parameters.get("n_shuffles",      500))
        track_len = float(parameters.get("track_length_cm", 160.0))
        min_bins  = int(parameters.get("min_pos_bins",    5))

        frames_meta = frames_nd.metadata.get("frames", [])
        posteriors  = decoded.metadata.get("posteriors", {})
        state_keys  = decoded.metadata.get("state_keys",  list(posteriors.keys()))
        bin_centers = np.asarray(decoded.metadata.get("bin_centers", []), dtype=np.float64)
        dec_times   = decoded.timestamps            # bin-centre times (s)

        if dec_times is None or len(dec_times) == 0:
            raise ValueError("decode_waking_rest_replay: decoded has no timestamps.")
        if not state_keys:
            raise ValueError("decode_waking_rest_replay: no state keys in decoded output.")

        rng = np.random.default_rng(42)
        results: list[dict] = []

        # Build a lookup from state_key → direction (1 or 2)
        def _direction(key: str) -> int:
            if key.endswith("_dir1"):
                return 1
            if key.endswith("_dir2"):
                return 2
            return 0

        for fidx, frame in enumerate(frames_meta):
            ft0 = float(frame["t_start"])
            ft1 = float(frame["t_end"])

            # Slice time index
            t_mask = (dec_times >= ft0) & (dec_times <= ft1)
            if t_mask.sum() < min_bins:
                continue

            for skey in state_keys:
                post = posteriors.get(skey)        # (n_pos, n_time_session)
                if post is None:
                    continue

                pdf_frame = post[:, t_mask]         # (n_pos, n_frame_bins)

                # Drop all-uniform columns
                stdp  = pdf_frame.std(axis=0)
                valid = stdp > 1e-12
                if valid.sum() < min_bins:
                    continue

                pdf_v = pdf_frame[:, valid]         # (n_pos, n_valid_bins)

                # ── Observed quality measures ─────────────────────────────
                wc      = _weighted_correlation(pdf_v)
                maxj_cm = _max_jump(pdf_v, bin_centers) if len(bin_centers) > 0 else np.nan

                # ── Shuffle distribution ──────────────────────────────────
                shuf_wc = np.empty(n_shuf, dtype=np.float64)
                for si in range(n_shuf):
                    perm     = rng.permutation(pdf_v.shape[1])
                    shuf_wc[si] = _weighted_correlation(pdf_v[:, perm])

                # Percentile of observed wc among shuffles
                wc_pct = float(np.sum(shuf_wc < wc) / n_shuf * 100.0)
                is_sig = (wc_pct < 2.5) or (wc_pct > 97.5)

                norm_maxj = (maxj_cm / track_len) if (not np.isnan(maxj_cm) and track_len > 0) else np.nan

                results.append({
                    "frame_idx":       fidx,
                    "t_start":         ft0,
                    "t_end":           ft1,
                    "state_key":       skey,
                    "direction":       _direction(skey),
                    "wc":              float(wc)       if not np.isnan(wc)       else np.nan,
                    "max_jump_cm":     float(maxj_cm)  if not np.isnan(maxj_cm)  else np.nan,
                    "norm_max_jump":   float(norm_maxj) if not np.isnan(norm_maxj) else np.nan,
                    "wc_pct":          wc_pct,
                    "is_sig":          bool(is_sig),
                    "n_active_cells":  frame.get("n_active_cells", 0),
                    "n_spikes":        frame.get("n_spikes", 0),
                    "mean_pos_cm":     frame.get("mean_pos_cm", np.nan),
                    # Store the posterior slice for later plotting
                    "pdf":             pdf_v.astype(np.float32),
                    "bin_centers":     bin_centers.tolist(),
                    "t_bins":          dec_times[t_mask][valid].tolist(),
                })

        # ── Summary statistics ────────────────────────────────────────────────
        n_frames_total   = len(frames_meta)
        # Each (frame × direction) pair is an independent representation.
        # Using unique-frame counting would understate the denominator and
        # inflate the apparent significance when multiple directions are tested.
        n_representations = len(results)           # frames × n_directions
        n_sig             = sum(1 for r in results if r["is_sig"])
        sig_ratio         = float(n_sig / n_representations) if n_representations > 0 else 0.0

        # Summary array: (n_results, 5) = [t_start, t_end, wc, norm_max_jump, is_sig]
        if results:
            arr = np.array(
                [[r["t_start"], r["t_end"], r["wc"], r["norm_max_jump"],
                  float(r["is_sig"])]
                 for r in results],
                dtype=np.float64,
            )
        else:
            arr = np.zeros((0, 5), dtype=np.float64)

        return {
            "replay_results": NeuroData(
                data_type  = "replay_results",
                array      = arr,
                timestamps = dec_times,
                metadata   = {
                    "results":          results,
                    "n_frames":         n_frames_total,
                    "n_representations": n_representations,
                    "n_sig_frames":     n_sig,
                    "sig_ratio":        sig_ratio,
                    "track_length_cm": track_len,
                    "state_keys":      state_keys,
                    "bin_centers":     bin_centers.tolist(),
                    "n_shuffles":      n_shuf,
                },
            )
        }
