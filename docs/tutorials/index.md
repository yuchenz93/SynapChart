# Tutorials

Step-by-step guides that walk you through building real neuroscience analysis workflows in SynapChart.

## Tutorial 1 — Theta Phase Precession

Build a complete hippocampal phase precession pipeline from scratch: load raw recordings, filter and extract theta phase, smooth and linearize position, compute a place field, visualize the precession scatter plot, create a custom quantification block, and package the whole workflow as a reusable composite block.

[Start Tutorial 1 →](tutorial1.md)

## Tutorial 2 — Batch Processing with the Dataset Iterator

Take the composite block from Tutorial 1 and run it automatically across all three sessions using a CSV file and the Dataset Iterator block. Learn how Collect Results accumulates per-iteration outputs into a single array for downstream analysis.

[Start Tutorial 2 →](tutorial2.md)

## Tutorial 3 — Theta Sequences with Real Hippocampal Data

Load a real session from the public CRCNS HC-11 dataset and run a complete theta sequence analysis. Learn how running direction is used as a behavioral state key to drive parallel analysis branches — separate tuning curves, Bayesian decoding, and theta sequence averaging for each direction — producing direction-specific heatmaps that reveal the hippocampus sweeping through a prospective spatial trajectory on every theta cycle.

[Start Tutorial 3 →](tutorial3.md)
