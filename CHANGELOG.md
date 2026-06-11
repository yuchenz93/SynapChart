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
- Security: load-time consent gate for workflows containing custom code.
  Opening a workflow with local blocks or embedded (packed) block sources now
  returns a code manifest **without executing anything**; the embedded Python is
  registered only after the user reviews it and confirms via the new
  CodeConsentModal. Built-in templates remain trusted. Documented in
  `SECURITY.md`.
- Test suite (77 tests) covering the reproducibility-critical core: DAG
  resolution, checkpoint cache-key derivation/invalidation, port + workflow
  validation, v1→v2 schema migration, and the execution engine (linear runs,
  cache reuse, parameter invalidation, error reporting, and batch iteration
  with the dataset iterator / collect-results path). Adds `pytest`
  configuration (`asyncio_mode = "auto"`) and shared fixtures in
  `backend/tests/conftest.py`.
