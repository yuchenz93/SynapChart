# LFP / EEG Blocks

Blocks for continuous signal processing: filtering, phase extraction, PSD, oscillation detection, and channel selection.

---

## Bandpass Filter
`bandpass_filter`

Zero-phase Butterworth bandpass filter applied to a continuous signal.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `signal` | Input | `NeuroData[raw_signal]` | Continuous signal to filter |
| `filtered` | Output | `NeuroData[lfp]` | Bandpass-filtered signal |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `low_hz` | float | `4.0` | Lower cutoff frequency (Hz) |
| `high_hz` | float | `12.0` | Upper cutoff frequency (Hz) |
| `order` | int | `4` | Filter order |

---

## Extract Phase
`extract_phase`

Extracts instantaneous phase via the Hilbert transform. Output is phase in radians (−π to π).

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `signal` | Input | `NeuroData[lfp]` | Band-limited signal (e.g. theta-filtered LFP) |
| `phase` | Output | `NeuroData[raw_signal]` | Instantaneous phase in radians (−π to π) |

**Parameters**

_None._

---

## Detect Theta Cycles
`detect_theta_cycles`

Detects individual theta cycle boundaries from an instantaneous-phase signal. Cycles are defined peak-to-peak (ascending zero-crossings of the Hilbert phase), so within each cycle the phase runs from 0° to 360° — the natural convention for phase precession analysis.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `phase` | Input | `NeuroData[raw_signal]` | Instantaneous phase in radians from `extract_phase` |
| `theta_cycles` | Output | `NeuroData[theta_cycles]` | (N_cycles × 2) array of [t_start, t_end] in seconds |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_cycle_dur` | float | `0.05` | Minimum valid cycle duration in seconds |
| `max_cycle_dur` | float | `0.25` | Maximum valid cycle duration in seconds |
| `channel_index` | int | `0` | Which channel to use if phase is multi-channel |

---

## Compute PSD
`compute_psd`

Computes power spectral density using Welch's method. Frequencies are stored in the `timestamps` field of the output.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `signal` | Input | `NeuroData[raw_signal]` | Continuous signal |
| `psd` | Output | `NeuroData[raw_signal]` | PSD array (power values); frequencies stored in `timestamps` |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `window_seconds` | float | `1.0` | Welch window length in seconds |
| `overlap` | float | `0.5` | Fractional overlap between windows (0–1) |

---

## Detect Oscillation Epochs
`detect_oscillation_epochs`

Detects epochs where instantaneous power exceeds a z-score threshold above the mean envelope (e.g. theta bouts or ripples).

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `signal` | Input | `NeuroData[lfp]` | Band-limited signal |
| `epochs` | Output | `NeuroData[raw_signal]` | N × 2 array of [start, stop] timestamps in seconds |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `threshold_sd` | float | `2.0` | Threshold in standard deviations above mean envelope |
| `min_duration_sec` | float | `0.1` | Minimum epoch duration in seconds |

---

## Select LFP Channel
`select_channel`

Extracts one channel from a multi-channel `NeuroData[lfp]` and returns a 1-D `NeuroData[lfp]` suitable for downstream filtering and phase extraction.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `lfp` | Input | `NeuroData[lfp]` | Multi-channel LFP (n_samples × n_channels) |
| `channel` | Output | `NeuroData[lfp]` | Single-channel LFP (n_samples,) |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `channel_index` | int | `0` | Zero-based index of the channel to extract |

---

## Select Channel
`select_reference_channel`

Selects a single channel from a generic multi-channel `NeuroData[raw_signal]`. Use this when the signal has not yet been typed as LFP.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `signal` | Input | `NeuroData[raw_signal]` | Multi-channel signal (N_samples × N_channels) |
| `channel` | Output | `NeuroData[raw_signal]` | Single-channel signal (N_samples,) |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `channel_index` | int | `0` | Zero-based index of the channel to extract |
