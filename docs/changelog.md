# Changelog

All notable changes to SynapChart are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/); versioning follows
[Semantic Versioning](https://semver.org/). The authoritative copy is
[`CHANGELOG.md`](https://github.com/yuchenz93/SynapChart/blob/main/CHANGELOG.md) in
the repository.

---

## [Unreleased]

### Changed

- **Port Type System v2.** Replaced the closed "registered data types" list and the
  fixed compatibility table with a two-axis model: a **structural type**
  (container / dtype / ndim / timed) that is enforced, plus a **free-form, advisory
  role** (e.g. `lfp`, `spike_times`, or anything you invent). Connection validation
  is now three-state — **OK** / **WARN** (role mismatch, still connectable) /
  **ERROR** (structural mismatch, blocked) — and new roles can be added in custom
  blocks without editing any core file. See [NeuroData](neurodata.md).

### Added

- Initial project scaffold: FastAPI backend, React + React Flow frontend.
- The `NeuroData` envelope type and the port validator (now the v2 model above).
- Block registry with auto-discovery, and the built-in block libraries: Data I/O,
  Behavior, LFP/EEG, Spikes, Visualization, and Flow Control, plus the 1D-Maze and
  2D-Maze analysis libraries.
- CLI entry point (the `synapchart` command) and `pyproject.toml` for pip
  distribution.
- GitHub Actions CI (test matrix: Python 3.10 / 3.11 / 3.12) and a release
  workflow that publishes to PyPI on a version tag.
- **Security:** a load-time consent gate for workflows containing custom code —
  opening a workflow with local or embedded blocks returns a code manifest
  **without executing anything**; embedded Python is registered only after you
  review and confirm it. Built-in templates remain trusted. Documented in
  [`SECURITY.md`](https://github.com/yuchenz93/SynapChart/blob/main/SECURITY.md).
- Test suite covering the reproducibility-critical core: DAG resolution, checkpoint
  cache-key derivation/invalidation, port + workflow validation, schema migration,
  and the execution engine (linear runs, cache reuse, parameter invalidation, error
  reporting, and batch iteration).

---

!!! note "No tagged release yet"
    SynapChart is in active pre-release development (Alpha). Changes above are on
    the `main` branch; the first versioned PyPI release will appear here when a
    version tag is cut.
