# SynapChart — Doc 05: Demo Workflow (Theta Phase Precession + Theta Sequences)

## Purpose

This document specifies the template workflow that ships with SynapChart v1. It serves two purposes:
1. A working demonstration that exercises the full pipeline
2. A test that all required built-in blocks are correctly implemented

The workflow computes theta phase precession and theta sequences from hippocampal recordings: LFP-derived theta phase + spike times + position are combined to show that place cell firing systematically shifts in phase as the animal crosses a place field, and to reconstruct the spatial sequence of cell activation within each theta cycle.

---

## Scientific Steps

The workflow implements the following analysis pipeline:

```
[LFP file]         [Spike file]       [Position file]
     │                   │                   │
Load LFP           Load spikes         Load position
     │                   │                   │
Select channel     Bin spikes          Smooth position
     │                   │                   │
Bandpass           Firing rate         Linearize position
(4–12 Hz)               │                   │
     │             Tuning curve ◄──────────── │
Extract phase           │                   │
     │                  │                   │
     ├──────────────────►├──────────────────►│
     │           Phase precession            │
     │           scatter plot                │
     │                  │                   │
     │           Bayesian decoder ◄──────────┘
     │           (spike matrix + tuning curves)
     │                  │
     │           Decoded posterior
     │                  │
     └──────────────────►
                Theta sequence plot
```

---

## Workflow JSON

Save this file as `workflows/templates/theta_phase_precession.json`.

```json
{
  "schema_version": "1.0",
  "name": "Theta phase precession and theta sequences",
  "description": "Computes theta phase precession and Bayesian-decoded theta sequences from hippocampal LFP, spike times, and position data. Requires three input files: a raw LFP .npy file, a spike times .npy file (1-D array of spike timestamps in seconds), and a position .npy file (N×3: time, x, y).",
  "created_at": "2025-01-01T00:00:00Z",
  "modified_at": "2025-01-01T00:00:00Z",
  "nodes": [

    {
      "node_id": "load_lfp_001",
      "block_type_id": "load_npy",
      "position": { "x": 80, "y": 80 },
      "parameters": {
        "file_path": "",
        "sampling_rate": 1250.0,
        "data_type_override": "raw_signal"
      },
      "user_notes": "Load your raw LFP recording. Set file_path to your .npy file. Set sampling_rate to match your recording (default 1250 Hz)."
    },

    {
      "node_id": "select_ch_002",
      "block_type_id": "select_reference_channel",
      "position": { "x": 80, "y": 220 },
      "parameters": { "channel_index": 0 },
      "user_notes": "Select which LFP channel to use for theta phase. Change channel_index if needed."
    },

    {
      "node_id": "bandpass_003",
      "block_type_id": "bandpass_filter",
      "position": { "x": 80, "y": 360 },
      "parameters": { "low_hz": 4.0, "high_hz": 12.0, "order": 4 },
      "user_notes": "Theta bandpass filter (4–12 Hz). Adjust band if your theta peak differs."
    },

    {
      "node_id": "phase_004",
      "block_type_id": "extract_phase",
      "position": { "x": 80, "y": 500 },
      "parameters": {},
      "user_notes": "Extracts instantaneous theta phase via Hilbert transform."
    },

    {
      "node_id": "load_spikes_005",
      "block_type_id": "load_spike_times",
      "position": { "x": 380, "y": 80 },
      "parameters": {
        "file_path": "",
        "unit_index": 0
      },
      "user_notes": "Load spike times for one place cell unit. Set file_path. Change unit_index to select different units."
    },

    {
      "node_id": "bin_spikes_006",
      "block_type_id": "bin_spikes",
      "position": { "x": 380, "y": 220 },
      "parameters": { "bin_size_sec": 0.02, "t_start": 0.0, "t_stop": -1.0 },
      "user_notes": "Bins spikes into 20 ms time bins for the Bayesian decoder."
    },

    {
      "node_id": "firing_rate_007",
      "block_type_id": "compute_firing_rate",
      "position": { "x": 380, "y": 360 },
      "parameters": { "sigma_sec": 0.05, "bin_size_sec": 0.01 },
      "user_notes": "Smoothed firing rate, used for the tuning curve computation."
    },

    {
      "node_id": "load_pos_008",
      "block_type_id": "load_position",
      "position": { "x": 680, "y": 80 },
      "parameters": {
        "file_path": "",
        "x_col": 1,
        "y_col": 2,
        "time_col": 0,
        "sampling_rate": 30.0
      },
      "user_notes": "Load position data. Set file_path. Columns: time=0, x=1, y=2 by default."
    },

    {
      "node_id": "smooth_pos_009",
      "block_type_id": "smooth_position",
      "position": { "x": 680, "y": 220 },
      "parameters": { "sigma_seconds": 0.1 },
      "user_notes": "Smooth the raw position trace."
    },

    {
      "node_id": "linear_pos_010",
      "block_type_id": "linearize_position",
      "position": { "x": 680, "y": 360 },
      "parameters": { "method": "pca" },
      "user_notes": "Project 2-D position onto the linear track axis using PCA. Switch to manual_axis if PCA gives wrong orientation."
    },

    {
      "node_id": "tuning_curve_011",
      "block_type_id": "compute_tuning_curve",
      "position": { "x": 530, "y": 500 },
      "parameters": { "n_bins": 50, "min_occupancy_sec": 0.1, "smooth_sigma": 1.5 },
      "user_notes": "Compute the place field (tuning curve) for the selected unit."
    },

    {
      "node_id": "plot_tuning_012",
      "block_type_id": "plot_tuning_curve",
      "position": { "x": 530, "y": 640 },
      "parameters": {
        "title": "Place field",
        "x_label": "Position (cm)",
        "y_label": "Firing rate (Hz)",
        "show_on_run": true,
        "save_path": ""
      },
      "user_notes": "Visualize the place field. Set save_path to save the figure."
    },

    {
      "node_id": "plot_precession_013",
      "block_type_id": "plot_phase_precession",
      "position": { "x": 230, "y": 640 },
      "parameters": {
        "title": "Theta phase precession",
        "show_on_run": true,
        "save_path": "",
        "position_range": "auto"
      },
      "user_notes": "Scatter plot of spike phase vs. position. Each dot is one spike."
    },

    {
      "node_id": "decoder_014",
      "block_type_id": "bayesian_decoder",
      "position": { "x": 680, "y": 500 },
      "parameters": {
        "bin_size_sec": 0.02,
        "prior": "uniform"
      },
      "user_notes": "Bayesian population vector decoder. Reconstructs position from spike counts and the tuning curve."
    },

    {
      "node_id": "plot_decoded_015",
      "block_type_id": "plot_decoded_posterior",
      "position": { "x": 680, "y": 640 },
      "parameters": {
        "title": "Theta sequences (decoded posterior)",
        "show_on_run": true,
        "save_path": "",
        "colormap": "viridis"
      },
      "user_notes": "Heatmap of the posterior probability over position × time. Diagonal sweeps within theta cycles are theta sequences."
    }

  ],
  "edges": [
    { "edge_id": "e01", "source_node_id": "load_lfp_001",    "source_port_id": "data",         "target_node_id": "select_ch_002",    "target_port_id": "signal" },
    { "edge_id": "e02", "source_node_id": "select_ch_002",   "source_port_id": "channel",       "target_node_id": "bandpass_003",     "target_port_id": "signal" },
    { "edge_id": "e03", "source_node_id": "bandpass_003",    "source_port_id": "filtered",      "target_node_id": "phase_004",        "target_port_id": "signal" },
    { "edge_id": "e04", "source_node_id": "load_spikes_005", "source_port_id": "spikes",        "target_node_id": "bin_spikes_006",   "target_port_id": "spikes" },
    { "edge_id": "e05", "source_node_id": "load_spikes_005", "source_port_id": "spikes",        "target_node_id": "firing_rate_007",  "target_port_id": "spikes" },
    { "edge_id": "e06", "source_node_id": "load_pos_008",    "source_port_id": "position",      "target_node_id": "smooth_pos_009",   "target_port_id": "position" },
    { "edge_id": "e07", "source_node_id": "smooth_pos_009",  "source_port_id": "position",      "target_node_id": "linear_pos_010",   "target_port_id": "position" },
    { "edge_id": "e08", "source_node_id": "firing_rate_007", "source_port_id": "rate",          "target_node_id": "tuning_curve_011", "target_port_id": "spikes" },
    { "edge_id": "e09", "source_node_id": "linear_pos_010",  "source_port_id": "linear_pos",    "target_node_id": "tuning_curve_011", "target_port_id": "variable" },
    { "edge_id": "e10", "source_node_id": "tuning_curve_011","source_port_id": "tuning_curve",  "target_node_id": "plot_tuning_012",  "target_port_id": "tuning_curve" },
    { "edge_id": "e11", "source_node_id": "load_spikes_005", "source_port_id": "spikes",        "target_node_id": "plot_precession_013","target_port_id": "spikes" },
    { "edge_id": "e12", "source_node_id": "phase_004",       "source_port_id": "phase",         "target_node_id": "plot_precession_013","target_port_id": "phase" },
    { "edge_id": "e13", "source_node_id": "linear_pos_010",  "source_port_id": "linear_pos",    "target_node_id": "plot_precession_013","target_port_id": "position" },
    { "edge_id": "e14", "source_node_id": "bin_spikes_006",  "source_port_id": "spike_matrix",  "target_node_id": "decoder_014",      "target_port_id": "spike_matrix" },
    { "edge_id": "e15", "source_node_id": "tuning_curve_011","source_port_id": "tuning_curve",  "target_node_id": "decoder_014",      "target_port_id": "tuning_curves" },
    { "edge_id": "e16", "source_node_id": "decoder_014",     "source_port_id": "decoded",       "target_node_id": "plot_decoded_015", "target_port_id": "decoded" }
  ]
}
```

---

## Additional Block Required by This Workflow

The demo workflow uses `bayesian_decoder`, which is not listed in Doc 03's built-in block library. Add it to `backend/blocks/spikes/`.

### `bayesian_decoder`

Implements a memoryless Bayesian position decoder. For each time bin, computes the posterior probability over position bins given the observed spike counts and the tuning curves.

- **Inputs:**
  - `spike_matrix` → `NeuroData[spike_matrix]` — binned spike counts, shape (n_units × n_time_bins)
  - `tuning_curves` → `NeuroData[tuning_curve]` — firing rate tuning curves, shape (n_units × n_position_bins)
- **Outputs:**
  - `decoded` → `NeuroData[decoded]` — posterior probability matrix, shape (n_position_bins × n_time_bins)
- **Parameters:**
  - `bin_size_sec` (float, default 0.02) — time bin size in seconds, must match the bin_spikes block
  - `prior` (enum: uniform/empirical, default uniform) — spatial prior distribution

**Implementation note:** The standard Bayesian decoder formula is:

```
P(x | n) ∝ P(x) × ∏_i [ f_i(x)^n_i × exp(-τ × f_i(x)) ]
```

where `f_i(x)` is the tuning curve of unit i at position x, `n_i` is the spike count in the time bin, and `τ` is the bin duration. Compute in log space to avoid numerical underflow. Normalize each time column to sum to 1.

---

## Testing the Demo Workflow

To verify the demo workflow runs end-to-end, create a minimal synthetic dataset:

```python
# scripts/generate_test_data.py
import numpy as np

SR = 1250   # LFP sampling rate
T = 60.0    # recording duration seconds
t = np.arange(0, T, 1/SR)

# Synthetic LFP: theta oscillation (8 Hz) + noise
lfp = np.sin(2 * np.pi * 8 * t) + 0.3 * np.random.randn(len(t))
np.save("test_lfp.npy", lfp)

# Synthetic spikes: Poisson process, 5 Hz mean
spike_times = np.sort(np.random.uniform(0, T, size=int(5 * T)))
np.save("test_spikes.npy", spike_times)

# Synthetic position: linear track back-and-forth, 30 Hz
pos_sr = 30
t_pos = np.arange(0, T, 1/pos_sr)
x = 100 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.1 * t_pos))  # 0–100 cm
y = np.zeros_like(x)
position = np.column_stack([t_pos, x, y])
np.save("test_position.npy", position)

print("Test data files written: test_lfp.npy, test_spikes.npy, test_position.npy")
```

After generating the files, open the template workflow in SynapChart, set the three `file_path` parameters to the generated files, and run the pipeline. All six visualization windows should appear without errors.
