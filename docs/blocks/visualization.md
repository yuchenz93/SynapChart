# Visualization Blocks

Blocks that render matplotlib figures. All visualization blocks share two common parameters: `show_on_run` (display the figure in the viz panel) and `save_path` (write a PNG to disk).

---

## Plot Signal
`plot_signal`

Plots one or more continuous signals as time series.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `signal` | Input | `NeuroData[raw_signal]` | Signal to plot |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | str | `"Signal"` | Plot title |
| `t_start` | float | `0.0` | Start time to display (seconds) |
| `t_stop` | float | `-1.0` | Stop time to display; `-1` = full signal |
| `show_on_run` | bool | `true` | Emit figure to viz panel |
| `save_path` | str | `""` | PNG save path; empty = no save |

---

## Plot PSD
`plot_psd`

Plots power spectral density. Expects the output of the `compute_psd` block (frequencies in `timestamps`, power in `array`).

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `psd` | Input | `NeuroData[raw_signal]` | PSD data (frequencies in `timestamps`, power in `array`) |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | str | `"Power Spectral Density"` | Plot title |
| `log_scale` | bool | `true` | Use log scale on the y-axis |
| `show_on_run` | bool | `true` | Emit figure to viz panel |
| `save_path` | str | `""` | PNG save path |

---

## Plot Raster
`plot_raster`

Plots a spike raster for one or more units.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `spikes` | Input | `NeuroData[spike_times]` | Spike timestamps (seconds) |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | str | `"Spike Raster"` | Plot title |
| `t_start` | float | `0.0` | Start time (seconds) |
| `t_stop` | float | `-1.0` | Stop time; `-1` = full range |
| `show_on_run` | bool | `true` | Emit figure to viz panel |
| `save_path` | str | `""` | PNG save path |

---

## Plot Tuning Curve
`plot_tuning_curve`

Plots a single-cell 1-D tuning curve (place field or other variable).

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `tuning_curve` | Input | `NeuroData[tuning_curve]` | Tuning curve (bins × firing rate) |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | str | `"Tuning Curve"` | Plot title |
| `x_label` | str | `"Position (cm)"` | X-axis label |
| `y_label` | str | `"Firing rate (Hz)"` | Y-axis label |
| `show_on_run` | bool | `true` | Emit figure to viz panel |
| `save_path` | str | `""` | PNG save path |

---

## Plot Population Tuning Curves
`plot_population_tuning_curves`

Plots a grid of firing-rate-vs-position tuning curves for all cells in a population. Optionally overlays place field boundaries.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `tuning_curves` | Input | `NeuroData[tuning_curves_population]` | Population tuning curves (n_cells × n_bins) |
| `place_fields` | Input (optional) | `NeuroData[place_fields]` | Place field boundaries for shading |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cells_per_row` | int | `10` | Subplots per row |
| `max_cells` | int | `120` | Maximum cells to plot (0 = all) |
| `cell_filter` | enum | `pyramidal` | Which cell type to display: `all`, `pyramidal`, or `interneuron` |
| `close_all` | bool | `true` | Call `plt.close('all')` before plotting |
| `show_on_run` | bool | `true` | Emit figure to viz panel |
| `save_path` | str | `""` | PNG save path |

---

## Plot Phase Precession
`plot_phase_precession`

Plots spike phase vs. position as a scatter plot — the canonical theta phase precession visualisation.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `spikes` | Input | `NeuroData[spike_times]` | Spike timestamps (seconds) |
| `phase` | Input | `NeuroData[raw_signal]` | Instantaneous LFP phase (radians) |
| `position` | Input | `NeuroData[position]` | Linearised or 2-D position |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | str | `"Phase Precession"` | Plot title |
| `position_range` | str | `"auto"` | Position range: `"auto"` or `"min,max"` |
| `show_on_run` | bool | `true` | Emit figure to viz panel |
| `save_path` | str | `""` | PNG save path |

---

## Plot Phase Precession Summary
`plot_phase_precession_summary`

Shows per-cell phase-vs-position scatters and a histogram of Pearson *r* values across selected cells. Pyramidal-cell r values are highlighted.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `phase_precession` | Input | `NeuroData[phase_precession]` | Phase precession stats from `compute_phase_precession` |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cell_filter` | enum | `pyramidal` | Which cells to include: `all`, `pyramidal`, or `interneuron` |
| `max_scatter_cells` | int | `20` | Max individual scatter plots shown (0 = distribution only) |
| `close_all` | bool | `true` | Call `plt.close('all')` before plotting |
| `show_on_run` | bool | `true` | Emit figure to viz panel |
| `save_path` | str | `""` | PNG save path |

---

## Plot Decoded Posterior
`plot_decoded_posterior`

Plots the decoded posterior probability matrix as a heatmap over time.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `decoded` | Input | `NeuroData[decoded]` | Posterior matrix (positions × time bins) |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | str | `"Decoded Posterior"` | Plot title |
| `colormap` | str | `"viridis"` | Matplotlib colormap name |
| `show_on_run` | bool | `true` | Emit figure to viz panel |
| `save_path` | str | `""` | PNG save path |

---

## Plot Theta Sequences
`plot_theta_sequences`

Heatmap of averaged decoded posteriors aligned to the animal's position across theta cycles. X-axis: time relative to cycle trough (ms). Y-axis: position relative to animal (cm).

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `theta_sequences` | Input | `NeuroData[theta_sequence]` | Averaged theta sequence matrix from `compute_theta_sequences` |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `theta_freq_hz` | float | `8.0` | Assumed theta frequency (Hz); used for half-cycle markers |
| `ylim_cm` | float | `40.0` | Half-range of y-axis in cm (0 = auto) |
| `colormap` | str | `"hot"` | Matplotlib colormap name |
| `show_on_run` | bool | `true` | Emit figure to viz panel |
| `save_path` | str | `""` | PNG save path |

---

## Plot Run Laps
`plot_laps`

Shows linearised position (cm) vs time. Running laps are overlaid in blue (direction 1, descending) and orange (direction 2, ascending).

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `position` | Input | `NeuroData[position]` | Linearised 1-D position with timestamps (cm) |
| `laps` | Input | `NeuroData[laps]` | Lap table from `detect_run_laps` |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `t_window_s` | float | `120.0` | Seconds of recording to display (0 = full session) |
| `close_all` | bool | `true` | Call `plt.close('all')` before plotting |
| `show_on_run` | bool | `true` | Emit figure to viz panel |
| `save_path` | str | `""` | PNG save path |

---

## Plot Behavior Decoding
`plot_behavior_decoding`

Plots actual position (line) against MAP-decoded position (dots) for each running lap. Computes and reports median absolute decoding error in cm.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `decoded` | Input | `NeuroData[decoded]` | Posterior matrix (n_pos_bins × n_time_bins) from Bayesian decoder |
| `position` | Input | `NeuroData[position]` | Linearised 1-D position with timestamps (cm) |
| `laps` | Input | `NeuroData[laps]` | Lap table from `detect_run_laps` |
| `tuning_curves` | Input (optional) | `NeuroData[tuning_curves_population]` | Provides position bin centres |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_laps_shown` | int | `6` | Number of individual laps to show side-by-side (0 = all) |
| `close_all` | bool | `true` | Call `plt.close('all')` before plotting |
| `show_on_run` | bool | `true` | Emit figure to viz panel |
| `save_path` | str | `""` | PNG save path |
