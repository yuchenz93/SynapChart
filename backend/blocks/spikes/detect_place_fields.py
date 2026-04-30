"""Detect place fields from a population tuning-curve NeuroData.

For each cell, connected rate-map bins above ``peak_fraction`` × peak_rate
are grouped into candidate fields.  Fields narrower than ``min_field_bins``
are discarded.
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class DetectPlaceFields(BlockBase):
    """Detect place fields from population tuning curves."""

    block_type_id = "detect_place_fields"
    display_name  = "Detect Place Fields"
    category      = "Spikes"
    description   = (
        "Finds place fields in each cell's 1-D tuning curve by thresholding "
        "at a fraction of the peak rate and grouping contiguous bins."
    )

    inputs = [
        PortDefinition("tuning_curves", "NeuroData[tuning_curves_population]",
                       "Population tuning curves (n_cells × n_bins)."),
    ]
    outputs = [
        PortDefinition("place_fields", "NeuroData[place_fields]",
                       "Per-cell place field list in metadata."),
    ]
    parameters = [
        ParameterDefinition("peak_fraction",  "float", 0.2,
                            "Bins above (peak_fraction × peak_rate) are included in a field."),
        ParameterDefinition("min_field_bins", "int",   3,
                            "Minimum number of bins for a valid place field."),
        ParameterDefinition("min_peak_rate",  "float", 1.0,
                            "Minimum peak firing rate (Hz) for a cell to be considered."),
        ParameterDefinition("require_bilateral_cutoff", "bool", True,
                            "Discard fields whose boundary touches the first or last bin of "
                            "the track (likely truncated by the track endpoint, not a true "
                            "field boundary)."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        tc: NeuroData = inputs["tuning_curves"]

        rate_maps   = tc.array              # (n_cells, n_bins)

        peak_frac      = float(parameters.get("peak_fraction",          0.2))
        min_bins       = int(parameters.get("min_field_bins",            3))
        min_peak       = float(parameters.get("min_peak_rate",           1.0))
        bilateral_cut  = bool(parameters.get("require_bilateral_cutoff", True))
        n_total_bins   = rate_maps.shape[1]
        bin_centers = tc.timestamps         # (n_bins,)
        cell_ids    = tc.metadata.get("cell_ids", list(range(rate_maps.shape[0])))

        if bin_centers is None:
            bin_centers = np.arange(rate_maps.shape[1], dtype=float)

        fields_dict: dict[str, list[dict]] = {}

        for i, cid in enumerate(cell_ids):
            rate  = rate_maps[i]
            peak  = float(np.max(rate))
            if peak < min_peak:
                fields_dict[str(cid)] = []
                continue

            threshold = peak_frac * peak
            above     = rate >= threshold

            # Find connected regions
            cell_fields: list[dict] = []
            in_field = False
            f_start  = 0
            for b in range(len(rate)):
                if above[b] and not in_field:
                    in_field = True
                    f_start  = b
                elif (not above[b] or b == len(rate) - 1) and in_field:
                    f_end = b if not above[b] else b + 1
                    in_field = False
                    width = f_end - f_start
                    if width < min_bins:
                        continue
                    # Reject fields whose boundary touches a track endpoint
                    # (they are likely truncated, not genuine field boundaries)
                    if bilateral_cut and (f_start == 0 or f_end >= n_total_bins):
                        continue
                    peak_bin = int(f_start + np.argmax(rate[f_start:f_end]))
                    cell_fields.append({
                        "start_bin":  f_start,
                        "end_bin":    f_end - 1,
                        "peak_bin":   peak_bin,
                        "start_pos":  float(bin_centers[f_start]),
                        "end_pos":    float(bin_centers[f_end - 1]),
                        "peak_pos":   float(bin_centers[peak_bin]),
                        "peak_rate":  float(rate[peak_bin]),
                        "mean_rate":  float(np.mean(rate[f_start:f_end])),
                    })
            fields_dict[str(cid)] = cell_fields

        n_with_fields = sum(1 for v in fields_dict.values() if v)

        return {
            "place_fields": NeuroData(
                data_type = "place_fields",
                array     = np.zeros(1),   # placeholder
                metadata  = {
                    "fields":           fields_dict,
                    "cell_ids":         [str(c) for c in cell_ids],
                    "bin_centers":      bin_centers.tolist(),
                    "n_cells_total":    len(cell_ids),
                    "n_cells_with_fields": n_with_fields,
                    "pyr_ids":          tc.metadata.get("pyr_ids", []),
                    "int_ids":          tc.metadata.get("int_ids", []),
                },
            )
        }
