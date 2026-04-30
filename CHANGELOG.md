# Changelog

All notable changes to SynapChart are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- Initial project scaffold: FastAPI backend, React + React Flow frontend
- NeuroData type system with 8 registered data types
- Port type validator with full compatibility table
- Block registry with auto-discovery via pkgutil
- Built-in block library (v1):
  - Data I/O: load_npy, load_csv, save_npy, export_csv
  - Behavior: load_position, smooth_position, compute_speed, linearize_position
  - LFP/EEG: bandpass_filter, extract_phase, compute_psd, detect_oscillation_epochs, select_reference_channel
  - Spikes: load_spike_times, bin_spikes, compute_firing_rate, compute_tuning_curve, spike_phase_coupling
  - Visualization: plot_signal, plot_psd, plot_raster, plot_tuning_curve, plot_phase_precession, plot_decoded_posterior
- CLI entry point (`synapchart` command via click)
- `pyproject.toml` for pip distribution
- GitHub Actions CI (test matrix: Python 3.10/3.11/3.12)
- GitHub Actions release workflow (build + publish to PyPI on git tag)
