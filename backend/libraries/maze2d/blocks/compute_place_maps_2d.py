"""Compute 2D firing-rate place maps for all pyramidal cells.

Uses the 2D (x, y) position stored in position.metadata["two_d_location"]
(raw metres from CRCNS sessInfo).  Positions are multiplied by 100 to
convert to centimetres before binning.

Algorithm (mirroring CA_RunSeq_Prep_8Arm category-2 substep-3):
  1. (Optional) Clip position to the named epoch window from epochs_info.
  2. Remove bad-tracking stamps: samples where instantaneous 2D speed
     exceeds max_speed_cms (default 150 cm/s) are treated as NaN.
  3. Compute instantaneous 2D speed; keep only samples ≥ speed_threshold_cms.
  4. Build an occupancy map (seconds per bin, with Gaussian smoothing).
  5. For each pyramidal cell: spike map → smooth → divide by occupancy.
  6. Bins with occupancy < min_occupancy_s are set to NaN.

Output metadata layout::

    metadata["maps"]          → np.ndarray (n_cells, n_bins_x, n_bins_y) float32
    metadata["occupancy"]     → np.ndarray (n_bins_x, n_bins_y) float32  seconds
    metadata["valid_mask"]    → np.ndarray bool (n_bins_x, n_bins_y)
    metadata["bin_centers_x"] → list[float]  cm
    metadata["bin_centers_y"] → list[float]  cm
    metadata["bin_size_cm"]   → float
    metadata["cell_ids"]      → list[int]
    metadata["pos_ts"]        → np.ndarray  timestamps (s, within epoch)
    metadata["pos_1d_cm"]     → np.ndarray  1D position (cm)
    metadata["pos_2d_cm"]     → np.ndarray  (N, 2) 2D position (cm)
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class ComputePlaceMaps2d(BlockBase):
    """Compute 2D firing-rate maps for all cells."""

    block_type_id = "compute_place_maps_2d"
    display_name  = "Compute 2D Place Maps"
    category      = "maze2d / Analysis"
    description   = (
        "Bins the animal's 2D trajectory into a spatial grid and computes "
        "per-cell firing-rate maps.  Speed-filtered occupancy correction is "
        "applied and maps are Gaussian-smoothed.  Bad tracking stamps (speed > "
        "max_speed_cms) are discarded.  Optionally clips position to a named "
        "epoch from epochs_info."
    )

    inputs = [
        PortDefinition("spike_data",    "NeuroData[multi_spike_times]",
                       "Multi-cell spike times (full session)."),
        PortDefinition("position",      "NeuroData[position]",
                       "Linearised 1-D position with two_d_location in metadata."),
        PortDefinition("epochs_info",   "NeuroData[epochs]",
                       "Epoch boundaries (optional). When connected, position is "
                       "clipped to the named epoch.", required=False),
        PortDefinition("track_polygon", "NeuroData[track_polygon]",
                       "Polygon defining valid track region from define_track_polygon_2d "
                       "(optional). Positions outside the polygon are excluded.",
                       required=False),
    ]
    outputs = [
        PortDefinition("place_maps_2d", "NeuroData[place_maps_2d]",
                       "Per-cell 2D rate maps and maze occupancy."),
    ]
    parameters = [
        ParameterDefinition("epoch_name",          "str",   "MazeEpoch",
                            "Name of the epoch to clip position to when epochs_info "
                            "is connected.  Set to '' to skip clipping."),
        ParameterDefinition("max_speed_cms",        "float", 150.0,
                            "Maximum plausible 2D speed (cm/s).  Samples exceeding "
                            "this are treated as bad tracking stamps and excluded."),
        ParameterDefinition("bin_size_cm",          "float", 4.0,
                            "Spatial bin side length (cm)."),
        ParameterDefinition("speed_threshold_cms",  "float", 4.0,
                            "Minimum 2D speed (cm/s) to include a position sample."),
        ParameterDefinition("smooth_sigma_bins",    "float", 1.5,
                            "Gaussian smoothing σ in bins for rate maps."),
        ParameterDefinition("min_occupancy_s",      "float", 0.05,
                            "Bins with occupancy < this (s) are set to NaN."),
        ParameterDefinition("pyr_only",             "bool",  True,
                            "If True, compute maps only for pyramidal cells."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        from scipy.ndimage import gaussian_filter

        spikes:   NeuroData = inputs["spike_data"]
        pos_nd:   NeuroData = inputs["position"]
        ep_nd:    NeuroData | None = inputs.get("epochs_info",   None)
        poly_nd:  NeuroData | None = inputs.get("track_polygon", None)

        epoch_name  = str(parameters.get("epoch_name",          "MazeEpoch"))
        max_spd_cms = float(parameters.get("max_speed_cms",      150.0))
        bin_size    = float(parameters.get("bin_size_cm",         4.0))
        speed_thr   = float(parameters.get("speed_threshold_cms", 4.0))
        sigma       = float(parameters.get("smooth_sigma_bins",   1.5))
        min_occ     = float(parameters.get("min_occupancy_s",     0.05))
        pyr_only    = bool(parameters.get("pyr_only",             True))

        # ── Position & timestamps ─────────────────────────────────────────────
        pos_ts  = pos_nd.timestamps
        pos_sr  = pos_nd.sampling_rate or 39.0
        if pos_ts is None:
            pos_ts = np.arange(len(pos_nd.array)) / pos_sr
        pos_ts = np.asarray(pos_ts, dtype=np.float64)

        pos_1d_cm = pos_nd.array.flatten().astype(np.float64)
        pos_2d_raw = pos_nd.metadata.get("two_d_location", None)
        if pos_2d_raw is None:
            raise ValueError("compute_place_maps_2d: position has no two_d_location.")
        pos_2d_cm = np.asarray(pos_2d_raw, dtype=np.float64) * 100.0  # m → cm

        # ── 1. Epoch clipping ─────────────────────────────────────────────────
        if ep_nd is not None and epoch_name:
            ep_meta = ep_nd.metadata
            bounds  = ep_meta.get(epoch_name, None)
            if bounds is not None:
                bounds = np.asarray(bounds).flatten()
                # May be [t_start, t_end] or [[t_start, t_end], ...]
                t_ep_start = float(bounds[0])
                t_ep_end   = float(bounds[-1])
                ep_mask = (pos_ts >= t_ep_start) & (pos_ts <= t_ep_end)
                pos_ts    = pos_ts[ep_mask]
                pos_1d_cm = pos_1d_cm[ep_mask]
                pos_2d_cm = pos_2d_cm[ep_mask]

        dt = float(np.median(np.diff(pos_ts))) if len(pos_ts) > 1 else 1.0 / pos_sr

        # ── 2. Bad-stamp removal (max speed filter on 2D coords) ──────────────
        if max_spd_cms > 0 and len(pos_ts) > 1:
            dx_raw = np.diff(pos_2d_cm[:, 0])
            dy_raw = np.diff(pos_2d_cm[:, 1])
            dt_raw = np.diff(pos_ts)
            dt_raw = np.where(dt_raw > 0, dt_raw, np.inf)
            inst_spd = np.sqrt(dx_raw ** 2 + dy_raw ** 2) / dt_raw  # cm/s

            # Mark the *later* sample of each jump as bad (conservative: mark both)
            bad = np.zeros(len(pos_ts), dtype=bool)
            bad[1:] |= (inst_spd > max_spd_cms)
            bad[:-1] |= (inst_spd > max_spd_cms)

            pos_2d_cm[bad] = np.nan
            pos_1d_cm[bad] = np.nan

        # ── 3. Spatial polygon mask ───────────────────────────────────────────
        if poly_nd is not None:
            vertices = poly_nd.metadata.get("vertices", [])
            if len(vertices) >= 3:
                from matplotlib.path import Path as MplPath
                poly_path = MplPath(np.array(vertices, dtype=np.float64))
                # Test all samples; NaN positions are treated as outside
                test_pts = pos_2d_cm.copy()
                test_pts[np.isnan(test_pts[:, 0]), :] = 1e12   # guaranteed outside
                outside = ~poly_path.contains_points(test_pts)
                pos_2d_cm[outside] = np.nan
                pos_1d_cm[outside] = np.nan

        # ── 5. Speed mask for running ─────────────────────────────────────────
        nan_mask_2d = np.isnan(pos_2d_cm[:, 0]) | np.isnan(pos_2d_cm[:, 1])

        # Compute 2D speed (NaN where position is NaN)
        dx = np.gradient(np.where(nan_mask_2d, np.nan, pos_2d_cm[:, 0]), pos_ts)
        dy = np.gradient(np.where(nan_mask_2d, np.nan, pos_2d_cm[:, 1]), pos_ts)
        speed_2d = np.sqrt(dx ** 2 + dy ** 2)

        run_mask = (~nan_mask_2d) & (speed_2d >= speed_thr)

        # ── 6. 2D grid ────────────────────────────────────────────────────────
        x_all = pos_2d_cm[~nan_mask_2d, 0]
        y_all = pos_2d_cm[~nan_mask_2d, 1]

        if len(x_all) == 0:
            raise ValueError("compute_place_maps_2d: no valid 2D positions remain "
                             "after epoch clipping and speed filtering.")

        x_min = float(np.floor(x_all.min() / bin_size) * bin_size)
        x_max = float(np.ceil( x_all.max() / bin_size) * bin_size)
        y_min = float(np.floor(y_all.min() / bin_size) * bin_size)
        y_max = float(np.ceil( y_all.max() / bin_size) * bin_size)

        x_edges = np.arange(x_min, x_max + bin_size, bin_size)
        y_edges = np.arange(y_min, y_max + bin_size, bin_size)
        bin_centers_x = (x_edges[:-1] + x_edges[1:]) / 2.0
        bin_centers_y = (y_edges[:-1] + y_edges[1:]) / 2.0
        n_x = len(bin_centers_x)
        n_y = len(bin_centers_y)

        # ── 7. Occupancy ──────────────────────────────────────────────────────
        occ_counts, _, _ = np.histogram2d(
            pos_2d_cm[run_mask, 0], pos_2d_cm[run_mask, 1],
            bins=[x_edges, y_edges],
        )
        occ_s = occ_counts * dt
        occ_s_sm = gaussian_filter(occ_s, sigma=sigma) if sigma > 0 else occ_s.copy()

        valid_mask = occ_s_sm >= min_occ

        # ── 8. Spike data ─────────────────────────────────────────────────────
        spike_times        = spikes.array
        cell_ids_per_spike = np.asarray(spikes.metadata.get("spike_cell_ids", []))
        pyr_ids_set        = set(spikes.metadata.get("pyr_ids", []))
        all_cell_ids = np.array(
            spikes.metadata.get("cell_ids",
                                sorted(np.unique(cell_ids_per_spike).tolist())),
            dtype=int,
        )
        cell_ids = (np.array(sorted(pyr_ids_set), dtype=int)
                    if pyr_only and pyr_ids_set else all_cell_ids)

        # ── 9. Rate maps ──────────────────────────────────────────────────────
        rate_maps = np.full((len(cell_ids), n_x, n_y), np.nan, dtype=np.float32)

        for ci, cid in enumerate(cell_ids):
            st = spike_times[cell_ids_per_spike == cid]
            if len(st) == 0:
                continue
            sp_x = np.interp(st, pos_ts, pos_2d_cm[:, 0], left=np.nan, right=np.nan)
            sp_y = np.interp(st, pos_ts, pos_2d_cm[:, 1], left=np.nan, right=np.nan)
            sp_speed = np.interp(st, pos_ts, speed_2d, left=0.0, right=0.0)

            valid_sp = (~np.isnan(sp_x)) & (~np.isnan(sp_y)) & (sp_speed >= speed_thr)
            if valid_sp.sum() == 0:
                rate_maps[ci, valid_mask] = 0.0
                continue

            spike_map, _, _ = np.histogram2d(
                sp_x[valid_sp], sp_y[valid_sp],
                bins=[x_edges, y_edges],
            )
            spike_map_sm = (gaussian_filter(spike_map.astype(float), sigma=sigma)
                            if sigma > 0 else spike_map.astype(float))

            with np.errstate(invalid="ignore", divide="ignore"):
                rate = np.where(occ_s_sm >= min_occ, spike_map_sm / occ_s_sm, np.nan)
            rate_maps[ci] = rate.astype(np.float32)

        return {
            "place_maps_2d": NeuroData(
                data_type = "place_maps_2d",
                array     = rate_maps,
                metadata  = {
                    "maps":           rate_maps,
                    "occupancy":      occ_s_sm.astype(np.float32),
                    "valid_mask":     valid_mask,
                    "bin_centers_x":  bin_centers_x.tolist(),
                    "bin_centers_y":  bin_centers_y.tolist(),
                    "bin_size_cm":    bin_size,
                    "cell_ids":       cell_ids.tolist(),
                    "pos_ts":         pos_ts,
                    "pos_1d_cm":      pos_1d_cm,
                    "pos_2d_cm":      pos_2d_cm,
                },
            )
        }
