# NeuroData

Every value that flows between blocks in a SynapChart pipeline is a `NeuroData` object. It is SynapChart's own data type — not a third-party library — defined in `backend/neurodata/types.py`.

Think of it as a numpy array with a label and a few standard neuroscience fields attached. The label (`data_type`) is what the port validator checks when you connect two blocks: it will warn you if you try to wire a `spike_times` output into an `lfp` input.

---

## Fields

| Field | Type | Description |
|-------|------|-------------|
| `data_type` | `str` | Type tag (e.g. `"lfp"`, `"spike_times"`). Controls port compatibility. |
| `array` | `np.ndarray` | The primary data payload — shape depends on the type. |
| `sampling_rate` | `float \| None` | Samples per second. `None` when not applicable (e.g. spike times). |
| `timestamps` | `np.ndarray \| None` | 1-D array of timestamps in seconds aligned to `array`. |
| `channel_names` | `list[str] \| None` | Channel labels, one per column of `array`. |
| `metadata` | `dict` | Freeform annotations. Each block documents the keys it adds. |

---

## Registered data types

The `data_type` field must be one of the registered strings below. The port validator uses these to decide whether two ports are compatible.

| Type tag | Array shape | Typical contents |
|----------|-------------|-----------------|
| `raw_signal` | (n_samples,) or (n_samples × n_channels) | Unprocessed continuous signal, any modality |
| `lfp` | (n_samples,) or (n_samples × n_channels) | Local field potential — same shape as `raw_signal`, typed for downstream validation |
| `spike_times` | (n_spikes,) | Spike timestamps in seconds for a single unit |
| `multi_spike_times` | (n_spikes,) | All spike timestamps across many cells; per-spike cell IDs stored in `metadata["spike_cell_ids"]` |
| `spike_matrix` | (n_units × n_time_bins) | Binned spike counts |
| `position` | (n_samples,) | Linearised 1-D position with timestamps |
| `tuning_curve` | (n_bins,) | Single-cell firing rate vs position |
| `tuning_curves_population` | (n_cells × n_bins) | Population rate maps; cell IDs in `channel_names` |
| `place_fields` | — | No primary array; field boundaries stored in `metadata["fields"]` |
| `phase_precession` | (n_cells,) | Mean Pearson *r* per cell; per-field detail in `metadata["results"]` |
| `decoded` | (n_pos_bins × n_time_bins) | Posterior probability matrix from Bayesian decoder |
| `theta_cycles` | (n_cycles × 2) | Peak-to-peak cycle boundaries [t_start, t_end] in seconds |
| `theta_sequence` | (n_time_per_cycle × n_pos_lags) | Averaged look-ahead/look-behind matrix |
| `epochs` | (2,) or (n_epochs × 2) | Epoch boundaries; named epochs in `metadata` |
| `laps` | — | Directional running bouts stored in `metadata["laps"]` |
| `any` | — | Wildcard — accepts any type. Used sparingly in I/O and flow-control blocks. |

---

## Port notation

Throughout the block reference, ports are written as `NeuroData[type_tag]`, for example:

```
NeuroData[lfp]          # a filtered LFP signal
NeuroData[spike_times]  # spike timestamps for one unit
NeuroData[decoded]      # posterior probability matrix
```

A port typed `NeuroData[any]` accepts any `NeuroData` object regardless of its `data_type`.

---

## Constructing a NeuroData (for custom blocks)

When writing a custom block, your `run()` method must return a `NeuroData` for each output port. Here is the minimal pattern:

```python
from neurodata.types import NeuroData
import numpy as np

return {
    "filtered": NeuroData(
        data_type="lfp",
        array=filtered_array,          # np.ndarray
        sampling_rate=1250.0,          # Hz
        timestamps=timestamps,         # 1-D array of seconds, or None
        channel_names=["ch0"],         # or None
        metadata={"low_hz": 4.0},      # any extra info downstream blocks might need
    )
}
```

Only `data_type` and `array` are required. All other fields default to `None` or `{}`.

!!! tip "Passing metadata forward"
    Many blocks forward the upstream metadata dict so context is not lost:
    ```python
    metadata={**signal.metadata, "low_hz": low, "high_hz": high}
    ```
    This is a convention, not a requirement, but it makes pipelines much easier to inspect and debug.
