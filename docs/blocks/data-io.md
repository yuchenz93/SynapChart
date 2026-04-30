# Data I/O Blocks

Blocks for loading data from disk and saving results. General-purpose blocks work with any array format; CRCNS I/O blocks are purpose-built for the HC-11 dataset.

---

## Load .npy file
`load_npy`

Loads a NumPy `.npy` or `.npz` file from disk and wraps it in a NeuroData envelope.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `data` | Output | `NeuroData[raw_signal]` | Loaded array |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | `""` | Absolute path to the `.npy` or `.npz` file |
| `sampling_rate` | float | `1000.0` | Samples per second |
| `data_type_override` | enum | `raw_signal` | Override the NeuroData type tag: `raw_signal`, `lfp`, `spike_times`, or `position` |

---

## Load CSV
`load_csv`

Loads a CSV file. If `has_timestamps` is true the first column is treated as timestamps (seconds) and excluded from the data array.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `data` | Output | `NeuroData[raw_signal]` | Loaded array |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | `""` | Absolute path to the CSV file |
| `has_timestamps` | bool | `true` | If true, first column is timestamps (seconds) |
| `sampling_rate` | float | `1000.0` | Sampling rate used when `has_timestamps` is false |

---

## Save .npy file
`save_npy`

Saves a NeuroData array to disk as a `.npy` file.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `data` | Input | `NeuroData[any]` | Data to save |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | `""` | Destination path (e.g. `/data/out.npy`) |
| `overwrite` | bool | `false` | If false, raises an error if the file already exists |

---

## Export CSV
`export_csv`

Exports a NeuroData array to a CSV file. Optionally prepends a timestamps column.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `data` | Input | `NeuroData[any]` | Data to export |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | `""` | Destination path (e.g. `/data/out.csv`) |
| `include_timestamps` | bool | `true` | If true, prepend the timestamps column |

---

## Load CRCNS Session
`load_crcns_session`

Reads `*_sessInfo.mat` from a CRCNS HC-11 session folder and returns multi-cell spike times, linearised 1-D position, and epoch boundaries. Requires the HDF5-format `.mat` file (MATLAB v7.3).

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `spike_data` | Output | `NeuroData[multi_spike_times]` | All spike times with per-spike cell IDs in metadata |
| `position` | Output | `NeuroData[position]` | Linearised 1-D position (cm) at ~39 Hz, maze epoch only |
| `epochs_info` | Output | `NeuroData[epochs]` | Epoch boundaries: MazeEpoch, PREEpoch, POSTEpoch, Wake, NREM, REM |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session_path` | str | `""` | Absolute path to the session folder (e.g. `.../Achilles_10252013`) |
| `cell_type_filter` | enum | `all` | `pyramidal` = PyrIDs only; `interneuron` = IntIDs only; `all` = both |
| `track_length_cm` | float | `160.0` | Known track length in cm; raw position range is scaled to `[0, track_length_cm]` |

---

## Load CRCNS LFP
`load_crcns_lfp`

Loads selected channels from a CRCNS HC-11 `baseName.eeg` file (int16, 1250 Hz). Connect a `NeuroData[epochs]` time range to avoid reading the full ~11 GB file.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `time_range` | Input (optional) | `NeuroData[epochs]` | Epoch window from `select_epoch`; overrides `t_start`/`t_end` parameters |
| `lfp` | Output | `NeuroData[lfp]` | LFP signal (n_samples × n_channels) at 1250 Hz |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session_path` | str | `""` | Path to the session folder (same folder as the `.eeg` file) |
| `channels` | str | `"0"` | Comma-separated channel indices or range, e.g. `"0,1,2"` or `"0-9"` |
| `t_start` | float | `-1.0` | Start time in seconds; `-1` = beginning of file |
| `t_end` | float | `-1.0` | End time in seconds; `-1` = end of file |
| `invert_signal` | bool | `false` | Multiply signal by −1 (for recordings with inverted polarity) |
