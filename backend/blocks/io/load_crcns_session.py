"""Load spike times, position and epoch info from a CRCNS hc-11 session folder.

The session folder must contain a ``*_sessInfo.mat`` file saved in MATLAB v7.3
format (HDF5 under the hood).  All times are in seconds as stored by the dataset.
"""


from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class LoadCrcnsSession(BlockBase):
    """Load spike times, linearised position and epoch info from CRCNS hc-11."""

    block_type_id = "load_crcns_session"
    display_name  = "Load CRCNS Session"
    category      = "CRCNS I/O"
    description   = (
        "Reads *_sessInfo.mat from a CRCNS hc-11 session folder and returns "
        "multi-cell spike times, linearised 1-D position, and epoch boundaries."
    )

    inputs = []
    outputs = [
        PortDefinition("spike_data",  "NeuroData[multi_spike_times]",
                       "All spike times with per-spike cell IDs in metadata."),
        PortDefinition("position",    "NeuroData[position]",
                       "Linearised 1-D position (metres) at ~39 Hz. Covers MAZE epoch only."),
        PortDefinition("epochs_info", "NeuroData[epochs]",
                       "Epoch boundaries: MazeEpoch, PREEpoch, POSTEpoch, Wake, NREM, REM …"),
    ]
    parameters = [
        ParameterDefinition(
            "session_path", "str", "",
            "Absolute path to the session folder, e.g. …/Achilles_10252013.",
        ),
        ParameterDefinition(
            "cell_type_filter", "enum:all,pyramidal,interneuron", "all",
            "'pyramidal' = PyrIDs only; 'interneuron' = IntIDs only; 'all' = both.",
        ),
        ParameterDefinition(
            "track_length_cm", "float", 160.0,
            "Known track length (cm). The raw OneDLocation range is linearly "
            "scaled so that [min, max] maps to [0, track_length_cm]. "
            "All downstream blocks assume position is in cm.",
        ),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import h5py

        session_path     = Path(str(parameters.get("session_path", "")).strip())
        cell_filter      = str(parameters.get("cell_type_filter", "all"))
        track_length_cm  = float(parameters.get("track_length_cm", 160.0))

        if not session_path.exists():
            raise FileNotFoundError(f"Session folder not found: {session_path}")

        mat_files = sorted(session_path.glob("*_sessInfo.mat"))
        if not mat_files:
            raise FileNotFoundError(f"No *_sessInfo.mat in {session_path}")
        mat_path = mat_files[0]

        with h5py.File(str(mat_path), "r") as f:
            si = f["sessInfo"]

            # ── Spikes ────────────────────────────────────────────────────
            spike_times = si["Spikes/SpikeTimes"][()].flatten().astype(np.float64)
            spike_ids   = si["Spikes/SpikeIDs"][()].flatten().astype(np.float64)
            pyr_ids     = np.unique(si["Spikes/PyrIDs"][()].flatten().astype(int))
            int_ids     = np.unique(si["Spikes/IntIDs"][()].flatten().astype(int))

            if cell_filter == "pyramidal":
                keep_ids = pyr_ids
            elif cell_filter == "interneuron":
                keep_ids = int_ids
            else:
                keep_ids = np.concatenate([pyr_ids, int_ids])

            mask = np.isin(spike_ids.astype(int), keep_ids)
            filt_times = spike_times[mask]
            filt_ids   = spike_ids[mask].astype(int)

            sort_idx   = np.argsort(filt_times)
            filt_times = filt_times[sort_idx]
            filt_ids   = filt_ids[sort_idx]

            # ── Position (already maze-epoch only) ───────────────────────
            pos_ts = si["Position/TimeStamps"][()].flatten().astype(np.float64)
            pos_1d = si["Position/OneDLocation"][()].flatten().astype(np.float64)
            pos_2d = si["Position/TwoDLocation"][()].T.astype(np.float32)  # (N, 2)

            # Interpolate NaN positions (tracking gaps)
            nan_mask = np.isnan(pos_1d)
            if nan_mask.any() and (~nan_mask).sum() > 1:
                valid = np.where(~nan_mask)[0]
                pos_1d = np.interp(np.arange(len(pos_1d)), valid, pos_1d[valid])

            # ── Scale position to cm ──────────────────────────────────────────
            # Raw OneDLocation may be in metres, pixels, or arbitrary units.
            # We map [min, max] → [0, track_length_cm] so all downstream blocks
            # can assume the unit is cm.
            p_raw_min = float(np.nanmin(pos_1d))
            p_raw_max = float(np.nanmax(pos_1d))
            p_raw_range = p_raw_max - p_raw_min
            if p_raw_range > 1e-9:
                pos_1d = (pos_1d - p_raw_min) / p_raw_range * track_length_cm
            else:
                pos_1d = np.zeros_like(pos_1d)

            # ── Epochs ───────────────────────────────────────────────────
            ep = si["Epochs"]
            epochs_meta: dict = {}
            for key in ep.keys():
                v = ep[key][()]
                # Shape (2, N): store as list of [start, end] pairs
                if v.ndim == 2 and v.shape[0] == 2:
                    epochs_meta[key] = v.T.tolist()   # [[s0,e0], [s1,e1], …]
                else:
                    epochs_meta[key] = v.flatten().tolist()

            maze_epoch = np.array(si["Epochs/MazeEpoch"][()]).flatten()

        pos_sr = float(1.0 / np.median(np.diff(pos_ts))) if len(pos_ts) > 1 else 39.0

        return {
            "spike_data": NeuroData(
                data_type     = "multi_spike_times",
                array         = filt_times,
                sampling_rate = None,
                metadata      = {
                    "spike_cell_ids":   filt_ids.tolist(),
                    "cell_ids":         sorted(np.unique(filt_ids).tolist()),
                    "pyr_ids":          pyr_ids.tolist(),
                    "int_ids":          int_ids.tolist(),
                    "n_cells":          int(len(np.unique(filt_ids))),
                    "cell_type_filter": cell_filter,
                    "session_path":     str(session_path),
                },
            ),
            "position": NeuroData(
                data_type     = "position",
                array         = pos_1d.astype(np.float32),
                sampling_rate = pos_sr,
                timestamps    = pos_ts,
                metadata      = {
                    "two_d_location":  pos_2d,
                    "t_start":         float(pos_ts[0]),
                    "t_end":           float(pos_ts[-1]),
                    "units":           "cm",
                    "track_length_cm": track_length_cm,
                },
            ),
            "epochs_info": NeuroData(
                data_type = "epochs",
                array     = maze_epoch.astype(np.float64),
                metadata  = epochs_meta,
            ),
        }
