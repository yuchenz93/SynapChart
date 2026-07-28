<div align="center">
  <img src="docs/assets/logo.svg" alt="SynapChart logo" width="120" />

  <h1>SynapChart</h1>

  <p><strong>Visual pipeline builder for neuroscience data analysis</strong></p>

  <p>
    <a href="https://pypi.org/project/synapchart/"><img alt="PyPI" src="https://img.shields.io/pypi/v/synapchart.svg"></a>
    <a href="https://pypi.org/project/synapchart/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/synapchart.svg"></a>
    <a href="https://yuchenz93.github.io/SynapChart/"><img alt="Documentation" src="https://img.shields.io/badge/docs-online-blue.svg"></a>
    <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
  </p>

  <p>
    <a href="https://yuchenz93.github.io/SynapChart/">Documentation</a> ·
    <a href="https://yuchenz93.github.io/SynapChart/getting-started/">Getting Started</a> ·
    <a href="https://yuchenz93.github.io/SynapChart/tutorials/">Tutorials</a> ·
    <a href="https://github.com/yuchenz93/SynapChart/issues">Report a bug</a>
  </p>
</div>

---

**SynapChart** is a drag-and-drop tool for building neuroscience analysis pipelines — think ComfyUI, but for spike trains and LFP signals. Connect blocks on an interactive canvas, wire up your data, and let the Python backend handle the computation. No boilerplate, no stitching scripts together — just your analysis, laid out visually and ready to share.

It runs entirely on your local machine: no cloud accounts, no data leaves your lab.

## Features

- **Visual & intuitive** — build EEG/LFP and spike-train analysis pipelines by dragging and connecting blocks on a canvas. No coding required.
- **Built for neuroscience** — native support for LFP, EEG, spike trains, and position data. Blocks for bandpass filtering, phase extraction, spike binning, tuning curves, theta phase precession, and more.
- **Open source & pip-installable** — one command to install, runs 100% locally.
- **Extensible** — write custom Python blocks and compose reusable sub-pipelines.

## Quickstart

```bash
pip install synapchart
synapchart
```

The browser opens automatically at `http://localhost:8000`.

📖 **Full documentation:** https://yuchenz93.github.io/SynapChart/

## What can you build?

SynapChart ships with worked tutorials using real hippocampal data, including:

- **Theta phase precession** — extract theta phase from LFP and relate it to place-cell spiking.
- **Theta sequences** with real CRCNS hippocampal recordings.
- **Batch processing** across sessions with the dataset iterator.

See the [Tutorials](https://yuchenz93.github.io/SynapChart/tutorials/) for step-by-step guides.

## Development setup

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev   # http://localhost:5173
```

## Tech stack

- **Frontend:** React + React Flow
- **Backend:** FastAPI (Python 3.10+)
- **Data format:** NeuroData (numpy wrapper with metadata)
- **Visualization:** matplotlib (server-side PNG)

## Keywords

Neuroscience data analysis · electrophysiology · EEG · LFP · spike trains · place cells · hippocampus · theta phase precession · visual programming · node-based pipeline · Python · open source

## License

[MIT](LICENSE) © Yuchen Zhou
