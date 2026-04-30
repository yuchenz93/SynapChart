# SynapChart

## Visual pipeline builder for neuroscience data analysis

SynapChart is a drag-and-drop tool for building neuroscience analysis pipelines — think ComfyUI, but for spike trains and LFP signals. Connect blocks on an interactive canvas, wire up your data, and let the Python backend handle the computation. No boilerplate, no stitching scripts together — just your analysis, laid out visually and ready to share.

---

## Why SynapChart?

<div class="grid cards" markdown>

-   :material-drag-variant:{ .lg .middle } **Visual & intuitive**

    ---

    Build analysis pipelines by dragging and connecting blocks on a canvas. See data flow through your pipeline in real time — no boilerplate code required.

-   :material-brain:{ .lg .middle } **Built for neuroscience**

    ---

    Native support for LFP, EEG, spike trains, and position data. Blocks for bandpass filtering, phase extraction, spike binning, tuning curves, and more — ready to use out of the box.

-   :material-open-source-initiative:{ .lg .middle } **Open source & pip-installable**

    ---

    One command to install. Runs entirely on your local machine — no cloud accounts, no data leaves your lab.

</div>

---

## Quick install

```bash
pip install synapchart
synapchart
```

The app opens automatically at `http://localhost:8000`.

!!! tip "First time here?"
    Head to [Getting Started](getting-started.md) for a walkthrough of your first pipeline.

---

## What can you do?

- **Theta phase precession analysis** — load hippocampal recordings, filter for theta, extract spike phases, and plot precession curves, all in a single visual workflow.
- **Batch processing across sessions** — wire a session-loader block to the rest of your pipeline and process an entire experiment in one run.
- **Build and share reusable blocks** — package a custom analysis as a `@block`-decorated function and share it with your lab as a plain Python file.

---

## Get started

[Get started :material-arrow-right:](getting-started.md){ .md-button .md-button--primary }
