# Spike Blocks

Blocks for spike train analysis: loading, binning, rate maps, tuning curves, place field detection, phase precession, and Bayesian decoding.

---

## Load Spike Times
`load_spike_times`

Loads spike times for one unit from a `.npy` or plain-text file.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `spikes` | Output | `NeuroData[spike_times]` | 1-D array of spike timestamps (seconds) |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | `""` | Path to spike times file (`.npy` or `.txt`) |
| `unit_index` | int | `0` | Unit index to load; `-1` concatenates all units |

---

## Bin Spikes
`bin_spikes`

Converts single-unit spike times to a binned spike-count array.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `spikes` | Input | `NeuroData[spike_times]` | 1-D spike timestamps (seconds) |
| `spike_matrix` | Output | `NeuroData[spike_matrix]` | Spike count array, shape (1 × N_bins) |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bin_size_sec` | float | `0.02` | Bin width in seconds |
| `t_start` | float | `0.0` | Start time in seconds |
| `t_stop` | float | `-1.0` | Stop time in seconds; `-1` uses the last spike time |

---

## Bin Population Spikes
`bin_population_spikes`

Converts multi-cell spike times into a (n_cells × n_time_bins) spike-count matrix compatible with the Bayesian decoder.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `spike_data` | Input | `NeuroData[multi_spike_times]` | Multi-cell spike times from `load_crcns_session` |
| `spike_matrix` | Output | `NeuroData[spike_matrix]` | (n_cells × n_time_bins) spike count matrix |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bin_size_sec` | float | `0.02` | Time bin width in seconds |

---

## Compute Firing Rate
`compute_firing_rate`

Computes a smoothed firing rate from spike times by convolving a spike-count histogram with a Gaussian kernel.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `spikes` | Input | `NeuroData[spike_times]` | 1-D spike timestamps (seconds) |
| `rate` | Output | `NeuroData[raw_signal]` | Smoothed firing rate in Hz |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sigma_sec` | float | `0.05` | Gaussian kernel standard deviation in seconds |
| `bin_size_sec` | float | `0.01` | Bin size for the intermediate count histogram |

---

## Compute Tuning Curve
`compute_tuning_curve`

Computes a 1-D tuning curve (firing rate as a function of a behavioural variable such as linearised position) for a single unit.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `spikes` | Input | `NeuroData[spike_times]` | 1-D spike timestamps (seconds) |
| `variable` | Input | `NeuroData[position]` | Behavioural variable sampled at a regular rate |
| `tuning_curve` | Output | `NeuroData[tuning_curve]` | Firing rate per bin (Hz) |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n_bins` | int | `50` | Number of spatial/variable bins |
| `min_occupancy_sec` | float | `0.1` | Minimum occupancy per bin (seconds) |
| `smooth_sigma` | float | `1.0` | Gaussian smoothing sigma in bins (0 = no smoothing) |

---

## Population Tuning Curves
`compute_population_tuning_curves`

Computes a firing-rate-vs-position tuning curve for every cell in a multi-cell recording. When laps are provided, analysis is restricted to running periods in the selected direction.

Default parameters assume position is in cm with a 160 cm track: 80 bins → 2 cm/bin, σ = 1.5 bins → ~3 cm smoothing.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `spike_data` | Input | `NeuroData[multi_spike_times]` | Multi-cell spike times with cell IDs in metadata |
| `position` | Input | `NeuroData[position]` | Linearised 1-D position with timestamps (cm) |
| `laps` | Input (optional) | `NeuroData[laps]` | Running laps from `detect_run_laps`; restricts analysis to running periods |
| `tuning_curves` | Output | `NeuroData[tuning_curves_population]` | (n_cells × n_bins) firing-rate matrix |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n_bins` | int | `80` | Number of position bins (80 bins over 160 cm = 2 cm/bin) |
| `smooth_sigma` | float | `1.5` | Gaussian smoothing σ in bins (~3 cm std at 2 cm/bin) |
| `min_occupancy` | float | `0.1` | Minimum occupancy (seconds) per bin to compute rate |
| `speed_threshold` | float | `5.0` | Minimum speed (cm/s) to include a position sample; 0 = no filter |
| `direction` | enum | `both` | Running direction: `1` = descending, `2` = ascending, `both` = all laps |

---

## Detect Place Fields
`detect_place_fields`

Finds place fields in each cell's tuning curve by thresholding at a fraction of the peak rate and grouping contiguous bins above threshold.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `tuning_curves` | Input | `NeuroData[tuning_curves_population]` | Population tuning curves (n_cells × n_bins) |
| `place_fields` | Output | `NeuroData[place_fields]` | Per-cell place field list in metadata |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `peak_fraction` | float | `0.2` | Bins above (peak_fraction × peak_rate) are included in a field |
| `min_field_bins` | int | `3` | Minimum number of bins for a valid field |
| `min_peak_rate` | float | `1.0` | Minimum peak firing rate (Hz) for a cell to be considered |
| `require_bilateral_cutoff` | bool | `true` | Discard fields whose boundary touches the first or last track bin (likely truncated) |

---

## Spike-Phase Coupling
`spike_phase_coupling`

Computes a spike-phase histogram: the distribution of spike phases relative to an LFP oscillation. Useful for quantifying theta-modulation of firing.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `spikes` | Input | `NeuroData[spike_times]` | 1-D spike timestamps (seconds) |
| `phase` | Input | `NeuroData[raw_signal]` | Instantaneous phase signal in radians |
| `phase_hist` | Output | `NeuroData[raw_signal]` | Phase histogram (counts per bin) |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n_bins` | int | `36` | Number of phase bins (default 36 = 10° per bin) |

---

## Compute Phase Precession
`compute_phase_precession`

For each cell and place field: collects within-field spikes (optionally restricted to direction-specific laps), interpolates theta phase and direction-corrected normalised position, and computes the Pearson linear correlation *r* and precession slope. Negative *r* indicates phase precession.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `spike_data` | Input | `NeuroData[multi_spike_times]` | Multi-cell spike times (maze epoch) |
| `phase` | Input | `NeuroData[raw_signal]` | Instantaneous theta phase in radians from `extract_phase` |
| `position` | Input | `NeuroData[position]` | Linearised 1-D position with timestamps |
| `place_fields` | Input | `NeuroData[place_fields]` | Per-cell place field boundaries |
| `laps` | Input (optional) | `NeuroData[laps]` | Running laps; when connected, only spikes during direction-matching laps are included |
| `phase_precession` | Output | `NeuroData[phase_precession]` | Per-cell × per-field *r* and slope values |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_spikes_per_field` | int | `10` | Minimum within-field spike count required to compute precession |
| `speed_threshold` | float | `5.0` | Minimum instantaneous speed (cm/s) to include a spike |
| `direction` | enum | `1` | Running direction: `1` = descending (high-end entry), `2` = ascending, `both` = all |

---

## Bayesian Decoder
`bayesian_decoder`

Memoryless Bayesian position decoder. Reconstructs position from binned spike counts and tuning curves using the formula P(x|n) ∝ P(x) × ∏ᵢ [fᵢ(x)^nᵢ × exp(−τ·fᵢ(x))], computed in log space.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `spike_matrix` | Input | `NeuroData[spike_matrix]` | Binned spike counts, shape (n_units × n_time_bins) |
| `tuning_curves` | Input | `NeuroData[tuning_curve]` | Firing-rate tuning curves, shape (n_units × n_position_bins) |
| `decoded` | Output | `NeuroData[decoded]` | Posterior probability matrix, shape (n_position_bins × n_time_bins) |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bin_size_sec` | float | `0.02` | Time bin duration in seconds; must match the `bin_spikes` block |
| `prior` | enum | `uniform` | Spatial prior: `uniform` (flat) or `empirical` (proportional to occupancy) |

---

## Compute Theta Sequences
`compute_theta_sequences`

Accumulates and averages decoded posteriors across theta cycles during running to reveal systematic look-ahead / look-behind (theta sequences). A symmetric ±`half_window_ms` window is extracted around each cycle trough.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `decoded` | Input | `NeuroData[decoded]` | Posterior probability matrix (n_pos_bins × n_time_bins) |
| `position` | Input | `NeuroData[position]` | Linearised 1-D position with timestamps |
| `theta_cycles` | Input | `NeuroData[theta_cycles]` | (N_cycles × 2) cycle boundaries from `detect_theta_cycles` |
| `tuning_curves` | Input (optional) | `NeuroData[tuning_curves_population]` | Provides position bin centres; estimated from position range if not connected |
| `laps` | Input (optional) | `NeuroData[laps]` | Running laps; only cycles within direction-matching laps are accumulated |
| `theta_sequences` | Output | `NeuroData[theta_sequence]` | (n_time_per_cycle × n_pos_lags) averaged sequence matrix |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n_time_per_cycle` | int | `36` | Number of temporal bins across the full window (~10 ms/bin at ±180 ms) |
| `half_window_ms` | float | `180.0` | Half-width of the time window centred at each cycle trough (ms); 180 ms spans ~3 theta cycles at 8 Hz |
| `min_speed` | float | `5.0` | Minimum running speed (cm/s) at cycle midpoint |
| `n_pos_lags` | int | `41` | Width of the look-ahead/behind axis in position bins (odd number) |
| `direction` | enum | `1` | Running direction to include: `1`, `2`, or `both` (only used when laps are connected) |
