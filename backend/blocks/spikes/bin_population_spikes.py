"""Bin multi-cell spike times into a (n_cells × n_time_bins) spike-count matrix.

Time range is taken from spike_data metadata (t_start / t_end) when available,
or from the spike times min/max.
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class BinPopulationSpikes(BlockBase):
    """Bin multi-cell spike times into a population spike-count matrix."""

    block_type_id = "bin_population_spikes"
    display_name  = "Bin Population Spikes"
    category      = "Spikes"
    description   = (
        "Converts multi_spike_times data into a (n_cells × n_time_bins) spike "
        "count matrix compatible with the Bayesian decoder."
    )

    inputs = [
        PortDefinition("spike_data", "NeuroData[multi_spike_times]",
                       "Multi-cell spike times from load_crcns_session / clip_spikes_to_epoch."),
    ]
    outputs = [
        PortDefinition("spike_matrix", "NeuroData[spike_matrix]",
                       "(n_cells × n_time_bins) spike count matrix."),
    ]
    parameters = [
        ParameterDefinition("bin_size_sec", "float", 0.02,
                            "Time bin width in seconds."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        spikes: NeuroData = inputs["spike_data"]
        bin_size = float(parameters.get("bin_size_sec", 0.02))

        spike_times = spikes.array
        cell_ids_per_spike = np.asarray(spikes.metadata.get("spike_cell_ids", []))
        cell_ids = np.array(
            spikes.metadata.get("cell_ids",
                                sorted(np.unique(cell_ids_per_spike).tolist())),
            dtype=int,
        )

        t_start = spikes.metadata.get("t_start", float(spike_times.min()) if len(spike_times) else 0.0)
        t_end   = spikes.metadata.get("t_end",   float(spike_times.max()) if len(spike_times) else 1.0)

        bins        = np.arange(t_start, t_end + bin_size, bin_size)
        n_bins      = len(bins) - 1
        bin_centers = (bins[:-1] + bins[1:]) / 2.0

        matrix = np.zeros((len(cell_ids), n_bins), dtype=np.float32)
        for i, cid in enumerate(cell_ids):
            if len(cell_ids_per_spike) == len(spike_times):
                st = spike_times[cell_ids_per_spike == cid]
            else:
                continue
            counts, _ = np.histogram(st, bins=bins)
            matrix[i] = counts

        return {
            "spike_matrix": NeuroData(
                data_type     = "spike_matrix",
                array         = matrix,
                sampling_rate = 1.0 / bin_size,
                timestamps    = bin_centers,
                channel_names = [str(c) for c in cell_ids],
                metadata      = {
                    "cell_ids":     cell_ids.tolist(),
                    "bin_size_sec": bin_size,
                    "t_start":      float(t_start),
                    "t_end":        float(t_end),
                    "n_cells":      len(cell_ids),
                },
            )
        }
