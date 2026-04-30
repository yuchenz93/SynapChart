"""Detect place fields from per-state population tuning curves.

For each state, applies the same connected-region thresholding algorithm as
detect_place_fields, producing per-state field lists.

Output metadata layout::

    metadata["fields_by_state"][state_name][cell_id_str]  →  list[field_dict]
    metadata["state_keys"]                                →  list[str]
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class DetectPlaceFields1d(BlockBase):
    """Detect place fields from per-state tuning curves (maze1d)."""

    block_type_id = "detect_place_fields_1d"
    display_name  = "Place Fields 1D"
    category      = "maze1d / Analysis"
    description   = (
        "Detects place fields in each cell's rate map for every state produced "
        "by compute_tuning_curves_1d.  Connected bins above "
        "peak_fraction × peak_rate are grouped into candidate fields; narrow or "
        "truncated fields are discarded."
    )

    inputs = [
        PortDefinition("tuning_curves", "NeuroData[tuning_curves_1d]",
                       "Per-state rate maps from compute_tuning_curves_1d."),
    ]
    outputs = [
        PortDefinition("place_fields", "NeuroData[place_fields_1d]",
                       "Per-state place field lists in metadata['fields_by_state']."),
    ]
    parameters = [
        ParameterDefinition("peak_fraction",  "float", 0.2,
                            "Bins above (peak_fraction × peak_rate) are in-field."),
        ParameterDefinition("min_field_bins", "int",   3,
                            "Minimum bin width of a valid place field."),
        ParameterDefinition("min_peak_rate",  "float", 1.0,
                            "Minimum peak firing rate (Hz) to consider a cell."),
        ParameterDefinition("require_bilateral_cutoff", "bool", True,
                            "Discard fields whose boundary touches the track endpoint."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        tc: NeuroData = inputs["tuning_curves"]

        peak_frac    = float(parameters.get("peak_fraction",           0.2))
        min_bins     = int(parameters.get("min_field_bins",             3))
        min_peak     = float(parameters.get("min_peak_rate",            1.0))
        bilateral    = bool(parameters.get("require_bilateral_cutoff",  True))

        rate_maps_by_state: dict[str, np.ndarray] = tc.metadata.get("rate_maps", {})
        state_keys  = tc.metadata.get("state_keys", list(rate_maps_by_state.keys()))
        cell_ids    = tc.metadata.get("cell_ids", [])
        bin_centers = np.asarray(tc.metadata.get("bin_centers",
                                                  tc.timestamps if tc.timestamps is not None
                                                  else np.arange(tc.array.shape[1])))

        def _detect(rate_maps: np.ndarray) -> dict[str, list[dict]]:
            n_total_bins = rate_maps.shape[1]
            fields: dict[str, list[dict]] = {}
            for i, cid in enumerate(cell_ids):
                rate = rate_maps[i]
                peak = float(np.max(rate))
                if peak < min_peak:
                    fields[str(cid)] = []
                    continue
                threshold = peak_frac * peak
                above     = rate >= threshold
                cell_flds: list[dict] = []
                in_field = False
                f_start  = 0
                for b in range(len(rate)):
                    if above[b] and not in_field:
                        in_field = True
                        f_start  = b
                    elif (not above[b] or b == len(rate) - 1) and in_field:
                        f_end    = b if not above[b] else b + 1
                        in_field = False
                        width    = f_end - f_start
                        if width < min_bins:
                            continue
                        if bilateral and (f_start == 0 or f_end >= n_total_bins):
                            continue
                        pk_bin = int(f_start + np.argmax(rate[f_start:f_end]))
                        cell_flds.append({
                            "start_bin": f_start,
                            "end_bin":   f_end - 1,
                            "peak_bin":  pk_bin,
                            "start_pos": float(bin_centers[f_start]),
                            "end_pos":   float(bin_centers[f_end - 1]),
                            "peak_pos":  float(bin_centers[pk_bin]),
                            "peak_rate": float(rate[pk_bin]),
                            "mean_rate": float(np.mean(rate[f_start:f_end])),
                        })
                fields[str(cid)] = cell_flds
            return fields

        fields_by_state: dict[str, dict] = {}
        for sname in state_keys:
            maps = rate_maps_by_state.get(sname)
            if maps is None:
                continue
            fields_by_state[sname] = _detect(maps)

        return {
            "place_fields": NeuroData(
                data_type = "place_fields_1d",
                array     = np.zeros(1),
                metadata  = {
                    "fields_by_state": fields_by_state,
                    "state_keys":      state_keys,
                    "cell_ids":        [str(c) for c in cell_ids],
                    "bin_centers":     bin_centers.tolist(),
                    "pyr_ids":         tc.metadata.get("pyr_ids", []),
                    "int_ids":         tc.metadata.get("int_ids", []),
                },
            )
        }
