"""Bayesian decode sleep frames and assess pre/replay significance.

For each detected sleep frame the block:
  1. Bins the spikes within the frame window into tau-second time bins.
  2. Applies the memoryless Bayesian decoder using the tuning curves obtained
     from the maze run (per direction).
  3. Computes quality measures (weighted correlation, normalised max jump).
  4. Shuffles the time columns of the posterior N times and flags the frame
     as significant if the observed wc falls outside the 2.5–97.5 % range.
  5. Tags each result with its epoch label ("pre" or "post").
  6. Computes per-epoch significant ratios and a plasticity test
     (Fisher's exact test: POST > PRE).

Output metadata layout::

    metadata["results"]               → list[dict] – one entry per (frame × dir)
        each dict has:
            frame_idx, t_start, t_end, epoch_label, state_key, direction,
            wc, max_jump_cm, norm_max_jump, wc_pct, is_sig,
            n_active_cells, n_spikes,
            pdf, bin_centers, t_bins
    metadata["n_frames"]              → int (total)
    metadata["n_frames_pre"]          → int
    metadata["n_frames_post"]         → int
    metadata["n_representations_pre"] → int
    metadata["n_representations_post"]→ int
    metadata["n_sig_pre"]             → int
    metadata["n_sig_post"]            → int
    metadata["sig_ratio_pre"]         → float
    metadata["sig_ratio_post"]        → float
    metadata["plasticity_pvalue"]     → float (Fisher exact, one-sided POST>PRE)
    metadata["track_length_cm"]       → float
    metadata["state_keys"]            → list[str]
    metadata["bin_centers"]           → list[float]
    metadata["n_shuffles"]            → int
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


# ---------------------------------------------------------------------------
# Pure helpers shared with decode_waking_rest_replay
# ---------------------------------------------------------------------------

def _weighted_correlation(pdf: np.ndarray) -> float:
    """Weighted correlation between time and position (Farooq 2019)."""
    np_bins, nt = pdf.shape
    if nt < 2 or np_bins < 2:
        return np.nan

    lpos = np.arange(1, np_bins + 1, dtype=np.float64)[:, None]
    lt   = np.arange(1, nt + 1,      dtype=np.float64)[None, :]

    total = pdf.sum()
    if total == 0:
        return np.nan

    mpos = (pdf * lpos).sum() / total
    mt   = (pdf * lt).sum()   / total

    dp = lpos - mpos
    dt = lt   - mt

    cov_pt = (pdf * dp * dt).sum() / total
    var_p  = (pdf * dp * dp).sum() / total
    var_t  = (pdf * dt * dt).sum() / total

    denom = np.sqrt(var_p) * np.sqrt(var_t)
    if denom < 1e-15:
        return np.nan
    return float(cov_pt / denom)


def _max_jump(pdf: np.ndarray, bin_centers: np.ndarray) -> float:
    """Maximum absolute position jump between successive decoded bins (cm)."""
    stdp  = pdf.std(axis=0)
    valid = stdp > 1e-12
    if valid.sum() < 2:
        return np.nan

    pdf_v   = pdf[:, valid]
    max_idx = pdf_v.argmax(axis=0)
    decoded = bin_centers[max_idx]
    jumps   = np.abs(np.diff(decoded))
    return float(jumps.max())


def _decode_frame(
    spike_times: np.ndarray,
    cell_ids_per_spike: np.ndarray,
    cell_ids: np.ndarray,
    rate_maps: np.ndarray,
    t0: float,
    t1: float,
    tau: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Bayesian decode spikes in [t0, t1] using rate_maps.

    Returns (posterior, bin_times) where posterior is (n_pos, n_valid_bins).
    rate_maps: (n_cells, n_pos)
    """
    bin_edges = np.arange(t0, t1 + tau, tau)
    if len(bin_edges) < 3:
        return np.zeros((rate_maps.shape[1], 0)), np.array([])

    bin_times = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    n_time    = len(bin_times)
    n_cells, n_pos = rate_maps.shape

    # Bin spikes per cell
    spike_matrix = np.zeros((n_cells, n_time), dtype=np.float32)
    for i, cid in enumerate(cell_ids):
        st = spike_times[cell_ids_per_spike == cid]
        if len(st) == 0:
            continue
        counts, _ = np.histogram(st, bins=bin_edges)
        spike_matrix[i] = counts

    eps     = 1e-10
    log_tc  = np.log(np.maximum(rate_maps, eps))      # (n_cells, n_pos)
    term1   = spike_matrix.T @ log_tc                  # (n_time, n_pos)
    term2   = tau * rate_maps.sum(axis=0)              # (n_pos,)
    lp      = term1 - term2                            # (n_time, n_pos)

    lp -= lp.max(axis=1, keepdims=True)
    post_T = np.exp(lp)
    col_sums = post_T.sum(axis=1, keepdims=True)
    col_sums = np.where(col_sums > 0, col_sums, 1.0)
    post_T  /= col_sums

    posterior = post_T.T.astype(np.float32)            # (n_pos, n_time)
    return posterior, bin_times


# ---------------------------------------------------------------------------
# Block
# ---------------------------------------------------------------------------

class DecodeSleepReplay(BlockBase):
    """Decode sleep frames and test pre/replay significance."""

    block_type_id = "decode_sleep_replay"
    display_name  = "Decode Sleep Replay"
    category      = "maze1d / Sleep"
    description   = (
        "Decodes each sleep frame (PRE and POST epochs) using the maze-run "
        "tuning curves.  Computes weighted correlation and normalised max jump "
        "quality metrics, runs N time-bin shuffles for significance, and "
        "computes significant pre/replay ratios.  Tests whether POST ratio "
        "exceeds PRE (plasticity) using Fisher's exact test."
    )

    inputs = [
        PortDefinition("spike_data",    "NeuroData[multi_spike_times]",
                       "Full-session spike times."),
        PortDefinition("tuning_curves", "NeuroData[tuning_curves_1d]",
                       "Per-state rate maps from compute_tuning_curves_1d."),
        PortDefinition("sleep_frames",  "NeuroData[sleep_frames]",
                       "Sleep frame intervals from detect_sleep_frames."),
    ]
    outputs = [
        PortDefinition("sleep_results", "NeuroData[sleep_results]",
                       "Per-frame quality metrics, significance flags, and "
                       "per-epoch summary statistics."),
    ]
    parameters = [
        ParameterDefinition("n_shuffles",      "int",   500,
                            "Number of time-column shuffles for significance."),
        ParameterDefinition("track_length_cm", "float", 160.0,
                            "Track length (cm) for jump normalisation."),
        ParameterDefinition("bin_size_sec",    "float", 0.02,
                            "Decoding time bin (s).  0.02 s matches the maze decoder."),
        ParameterDefinition("min_pos_bins",    "int",   5,
                            "Minimum decoded bins required to assess a frame."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        spikes:     NeuroData = inputs["spike_data"]
        tc:         NeuroData = inputs["tuning_curves"]
        frames_nd:  NeuroData = inputs["sleep_frames"]

        n_shuf    = int(parameters.get("n_shuffles",      500))
        track_len = float(parameters.get("track_length_cm", 160.0))
        tau       = float(parameters.get("bin_size_sec",    0.02))
        min_bins  = int(parameters.get("min_pos_bins",     5))

        frames_meta = frames_nd.metadata.get("frames", [])
        rate_maps_all = tc.metadata.get("rate_maps",   {})
        state_keys    = tc.metadata.get("state_keys",  list(rate_maps_all.keys()))
        bin_centers   = np.asarray(tc.metadata.get("bin_centers", []), dtype=np.float64)
        tc_cell_ids   = np.array(tc.metadata.get("cell_ids", []), dtype=int)

        # Align spike data to tuning-curve cell order
        spike_times        = spikes.array
        cell_ids_per_spike = np.asarray(spikes.metadata.get("spike_cell_ids", []))

        if len(tc_cell_ids) == 0:
            raise ValueError("decode_sleep_replay: no cell_ids in tuning_curves.")

        rng = np.random.default_rng(42)

        def _direction(key: str) -> int:
            if key.endswith("_dir1"):
                return 1
            if key.endswith("_dir2"):
                return 2
            return 0

        results: list[dict] = []

        for fidx, frame in enumerate(frames_meta):
            ft0         = float(frame["t_start"])
            ft1         = float(frame["t_end"])
            epoch_label = str(frame.get("epoch_label", "unknown"))

            # Spikes in this frame (all cells for decoding)
            in_frame    = (spike_times >= ft0) & (spike_times <= ft1)
            st_frame    = spike_times[in_frame]
            ci_frame    = cell_ids_per_spike[in_frame]

            for skey in state_keys:
                rate_maps = rate_maps_all.get(skey)
                if rate_maps is None:
                    continue

                rate_maps_arr = np.asarray(rate_maps, dtype=np.float32)
                # Align: rate_maps rows correspond to tc_cell_ids
                posterior, bin_times = _decode_frame(
                    st_frame, ci_frame, tc_cell_ids,
                    rate_maps_arr, ft0, ft1, tau,
                )

                if posterior.shape[1] < 1:
                    continue

                # Drop uniform columns
                stdp  = posterior.std(axis=0)
                valid = stdp > 1e-12
                if valid.sum() < min_bins:
                    continue

                pdf_v      = posterior[:, valid]
                t_bins_v   = bin_times[valid]

                # ── Observed quality measures ─────────────────────────────────
                wc      = _weighted_correlation(pdf_v)
                maxj_cm = _max_jump(pdf_v, bin_centers) if len(bin_centers) > 0 else np.nan

                # ── Shuffle distribution ──────────────────────────────────────
                shuf_wc = np.empty(n_shuf, dtype=np.float64)
                for si in range(n_shuf):
                    perm = rng.permutation(pdf_v.shape[1])
                    shuf_wc[si] = _weighted_correlation(pdf_v[:, perm])

                wc_pct = float(np.sum(shuf_wc < wc) / n_shuf * 100.0)
                is_sig = (wc_pct < 2.5) or (wc_pct > 97.5)

                norm_maxj = (maxj_cm / track_len) if (
                    not np.isnan(maxj_cm) and track_len > 0
                ) else np.nan

                results.append({
                    "frame_idx":       fidx,
                    "t_start":         ft0,
                    "t_end":           ft1,
                    "epoch_label":     epoch_label,
                    "state_key":       skey,
                    "direction":       _direction(skey),
                    "wc":              float(wc)       if not np.isnan(wc)       else np.nan,
                    "max_jump_cm":     float(maxj_cm)  if not np.isnan(maxj_cm)  else np.nan,
                    "norm_max_jump":   float(norm_maxj) if not np.isnan(norm_maxj) else np.nan,
                    "wc_pct":          wc_pct,
                    "is_sig":          bool(is_sig),
                    "n_active_cells":  frame.get("n_active_cells", 0),
                    "n_spikes":        frame.get("n_spikes", 0),
                    "pdf":             pdf_v.astype(np.float32),
                    "bin_centers":     bin_centers.tolist(),
                    "t_bins":          t_bins_v.tolist(),
                })

        # ── Per-epoch summary statistics ──────────────────────────────────────
        n_frames_total = len(frames_meta)
        n_frames_pre   = frames_nd.metadata.get("n_frames_pre",  0)
        n_frames_post  = frames_nd.metadata.get("n_frames_post", 0)

        pre_results  = [r for r in results if r["epoch_label"] == "pre"]
        post_results = [r for r in results if r["epoch_label"] == "post"]

        n_repr_pre  = len(pre_results)
        n_repr_post = len(post_results)

        n_sig_pre  = sum(1 for r in pre_results  if r["is_sig"])
        n_sig_post = sum(1 for r in post_results if r["is_sig"])

        sig_ratio_pre  = float(n_sig_pre  / n_repr_pre)  if n_repr_pre  > 0 else 0.0
        sig_ratio_post = float(n_sig_post / n_repr_post) if n_repr_post > 0 else 0.0

        # ── Plasticity test: Fisher's exact test (one-sided POST > PRE) ───────
        plasticity_pvalue = np.nan
        try:
            from scipy.stats import fisher_exact
            n_ns_pre  = n_repr_pre  - n_sig_pre
            n_ns_post = n_repr_post - n_sig_post
            # Contingency table:
            #              sig    not-sig
            # PRE       n_sig_pre   n_ns_pre
            # POST      n_sig_post  n_ns_post
            table = [[n_sig_pre,  n_ns_pre],
                     [n_sig_post, n_ns_post]]
            _, pval_two = fisher_exact(table, alternative="two-sided")
            # alternative="less": tests OR < 1, i.e. PRE sig rate < POST sig rate
            # (scipy OR = PRE_sig×POST_ns / PRE_ns×POST_sig; OR<1 ↔ POST rate > PRE rate)
            _, pval_one = fisher_exact(table, alternative="less")
            # one-sided p-value for POST sig rate > PRE sig rate
            plasticity_pvalue = float(pval_one)
        except Exception:
            pass

        # Summary array: (n_results, 6)
        if results:
            arr = np.array(
                [[r["t_start"], r["t_end"], r["wc"], r["norm_max_jump"],
                  float(r["is_sig"]),
                  1.0 if r["epoch_label"] == "post" else 0.0]
                 for r in results],
                dtype=np.float64,
            )
        else:
            arr = np.zeros((0, 6), dtype=np.float64)

        return {
            "sleep_results": NeuroData(
                data_type = "sleep_results",
                array     = arr,
                metadata  = {
                    "results":               results,
                    "n_frames":              n_frames_total,
                    "n_frames_pre":          n_frames_pre,
                    "n_frames_post":         n_frames_post,
                    "n_representations_pre":  n_repr_pre,
                    "n_representations_post": n_repr_post,
                    "n_sig_pre":             n_sig_pre,
                    "n_sig_post":            n_sig_post,
                    "sig_ratio_pre":         sig_ratio_pre,
                    "sig_ratio_post":        sig_ratio_post,
                    "plasticity_pvalue":     plasticity_pvalue,
                    "track_length_cm":       track_len,
                    "state_keys":            state_keys,
                    "bin_centers":           bin_centers.tolist(),
                    "n_shuffles":            n_shuf,
                },
            )
        }
