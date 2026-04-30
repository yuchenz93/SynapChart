# Getting Started

SynapChart currently focuses on extracellular electrophysiology — LFP, EEG, spike trains, and position tracking — with hippocampal circuits as the primary use case. Future versions will expand to calcium imaging, fMRI, and ECoG.

---

## Installation

**Requirements:** Python 3.10 or later.

```bash
pip install synapchart
synapchart
```

The browser opens automatically at `http://localhost:8000`.

---

## Quick orientation

- **Canvas** (center) — your workspace; drag blocks here and connect their ports to build a pipeline.
- **Block library** (left panel) — browse and search all available blocks; drag one onto the canvas to add it.
- **Toolbar** (top) — run the pipeline, open templates, save/load workflows, and access settings.

---

## Running the demo workflow: Theta Phase Precession

### Step 1 — Download the dataset

Download the HC-11 dataset from CRCNS:

[https://crcns.org/data-sets/hc/hc-11](https://crcns.org/data-sets/hc/hc-11)

!!! info "CRCNS account required"
    A free account at [crcns.org](https://crcns.org) is required to download. HC-11 is a publicly available hippocampal recording dataset containing simultaneous LFP, spike times, and animal position data.

### Step 2 — Load the template

In the SynapChart toolbar, click **Templates** and select:

> **Theta phase precession and theta sequences**

The canvas will populate with a pre-built pipeline of connected blocks.

### Step 3 — Point the loader blocks to your files

Three blocks at the start of the pipeline each need a file path. Click each one and browse to the files you downloaded:

| Block | File |
|---|---|
| LFP loader | LFP recording file |
| Spike times loader | Spike times file |
| Position loader | Position tracking file |

### Step 4 — Run the pipeline

Click **Run** in the toolbar. Block borders will highlight as each one executes in order.

### Step 5 — View the results

Three visualization windows will appear when the pipeline finishes:

1. **Place field tuning curve** — spatial firing rate map for each cell
2. **Theta phase precession scatter plot** — spike phase vs. position
3. **Decoded posterior heatmap** — Bayesian position reconstruction across theta cycles

!!! tip "Smart caching"
    On first run, all blocks execute from scratch. On subsequent runs, unchanged blocks load their outputs from cache automatically — only modified branches re-execute.

---

## Next steps

- [Block Reference](blocks/index.md) — browse all built-in blocks and their parameters
- [Custom Blocks](blocks/custom-blocks.md) — wrap your own Python functions as blocks
- [Composite Blocks](advanced/composite-blocks.md) — group a subgraph into a single reusable block
