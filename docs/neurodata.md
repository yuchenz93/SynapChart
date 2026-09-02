# NeuroData

Every value that flows between blocks in a SynapChart pipeline is a `NeuroData` object. It is SynapChart's own data type — not a third-party library — defined in `backend/neurodata/types.py`.

Think of it as a numpy array with a few standard neuroscience fields attached (sampling rate, timestamps, channel names) plus a short **role** label. When you connect two blocks, SynapChart checks both the **structure** of the payload (array shape and dtype, scalar, string, …) and the **role** — structure is enforced, while a role mismatch (say, a `spike_times` output into an `lfp` input) is just a friendly warning you can accept.

---

## Fields

| Field | Type | Description |
|-------|------|-------------|
| `data_type` | `str` | Free-form **role** tag (e.g. `"lfp"`, `"spike_times"`). Advisory — guides connections; see [How ports are typed](#how-ports-are-typed). |
| `array` | `np.ndarray` | The primary data payload — shape depends on the type. |
| `sampling_rate` | `float \| None` | Samples per second. `None` when not applicable (e.g. spike times). |
| `timestamps` | `np.ndarray \| None` | 1-D array of timestamps in seconds aligned to `array`. |
| `channel_names` | `list[str] \| None` | Channel labels, one per column of `array`. |
| `metadata` | `dict` | Freeform annotations. Each block documents the keys it adds. |

---

## How ports are typed

A port's type has **two independent parts**:

1. **Structure** — what the payload mechanically *is*. This is general, not
   neuroscience-specific: an N-dimensional numpy array (of floats, ints, or
   bools), a scalar (`float` / `int` / `bool`), a `str`, a list, and so on. For
   array payloads SynapChart also tracks the rank (1-D, 2-D, …) and whether the
   data carries per-sample timing. Structure is **enforced** — you can't wire a
   string into an array port — *when a port declares one*
   ([details below](#where-a-ports-structure-comes-from)).
2. **Role** — an optional, **free-form** label for what the data *means* in your
   domain (`lfp`, `spike_times`, `position`, or anything you invent). Roles are
   **advisory**: a mismatch shows a ⚠ warning you can accept — it never blocks.

There is **no fixed list of allowed types**. You can introduce a new role at any
time — in a custom block or a third-party library — without editing any core
file.

| Connection | When | Behaviour |
|---|---|---|
| ✅ **OK** | structure fits, roles agree | connects normally |
| ⚠ **Warning** | structure fits, roles differ | connects, flagged with a ⚠ badge |
| ⛔ **Blocked** | structure doesn't fit (e.g. a scalar into an array port) | rejected |

### Where a port's structure comes from

Wiring checks compare the two ports' **declared types** (from each block's
definition). The `NeuroData` value you return at run time is **not** inspected
during wiring — its `data_type` is only the role. A declared type resolves to a
structure in one of three ways:

- **Built-in role → implied structure (enforced).** SynapChart keeps a small
  table mapping each shipped role to its shape — effectively the *Common roles*
  table below. So a port declared `NeuroData[lfp]` is understood as *a float
  array that carries timing*, and that shape **is** checked — even though the
  `lfp` label itself is advisory.
- **Novel role → structurally open.** A port declared `NeuroData[my_metric]`
  (a role SynapChart has never seen) adds **no** structural constraint — only the
  role travels, so a mismatch warns but nothing is blocked.
- **Explicit structure → enforced, no role needed.** In a hand-written block you
  can pin the shape directly: `array<float,2d,timed>`, or a plain `float` /
  `int` / `str`.

```python
# In a block definition, the port's *declared type* is what gets enforced:

# built-in role — implied structure IS checked (float array, carries timing)
PortDefinition("filtered", "NeuroData[lfp]", "Filtered LFP")

# novel role — carries meaning but no shape constraint (structure = any)
PortDefinition("plv", "NeuroData[phase_locking]", "Custom phase-locking metric")

# explicit structure — enforced without a domain role
PortDefinition("weights", "array<float,2d>", "Weight matrix")
```

The **value** a block returns sets only the role, via `data_type`:

```python
return {"filtered": NeuroData(data_type="lfp", array=arr, sampling_rate=1250.0)}
# "lfp" here is the advisory role; the *enforced* shape came from the port's
# declared type above — not from this value.
```

### Common roles in the built-in library

These are **conventions used by the blocks that ship with SynapChart** — examples
to reuse or extend, not a closed set:

| Role | Array shape | Typical contents |
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

Throughout the block reference, ports are written `NeuroData[role]`, for example:

```
NeuroData[lfp]          # array payload with the role "lfp"
NeuroData[spike_times]  # spike timestamps for one unit
NeuroData[decoded]      # posterior probability matrix
```

The part in brackets is just the **role**. `NeuroData[any]` accepts anything.
Scalars and strings are written plainly (`float`, `int`, `bool`, `str`). When a
block cares about shape but not a domain role, structure can be declared directly
— e.g. `array<float,2d,timed>`.

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
