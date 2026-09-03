# Workflows

A **workflow** is a whole analysis pipeline: the blocks you've placed on the
canvas, the connections between their ports, and every parameter you've set. It is
the unit you save, load, run, and share.

## Anatomy of a workflow

| Part | What it is |
|---|---|
| **Nodes** | Block instances on the canvas (built-in, custom, or composite). |
| **Edges** | Connections from an output port to a compatible input port. |
| **Parameters** | Per-node settings you edit by double-clicking a block. |
| **Embedded block sources** | The Python source of any custom/composite block used, saved *inside* the workflow file so it is self-contained. |

## Running a workflow

Click **Run** to execute the whole graph. SynapChart resolves the dependency order
automatically (a topological sort of the DAG), runs each block once its inputs are
ready, and streams status + any `disp()` output to the Run Progress panel.

**Smart caching.** After the first run, each block caches its output keyed by its
inputs, parameters, and source. On the next run, unchanged blocks are skipped and
their cached outputs reused — only the branches you actually modified re-execute.
This keeps iteration fast even on large recordings.

## Saving, loading, and sharing

**Save** writes the current canvas to a `.json` file. The file is **self-contained**:
it embeds the definitions of any custom or composite blocks the workflow uses, so a
collaborator can open it without having those blocks installed.

!!! warning "Opening workflows that contain code"
    Because a saved workflow can carry custom Python, opening one that contains
    local or embedded blocks shows you a **code manifest first** and runs nothing
    until you review and approve it (built-in templates are trusted). See
    [`SECURITY.md`](https://github.com/yuchenz93/SynapChart/blob/main/SECURITY.md)
    for the consent model.

## Templates

**Templates** are ready-made workflows you can open as a starting point (toolbar →
**Templates**). Opening one drops a fully wired pipeline onto a new canvas tab;
modify it freely without affecting the original. The example templates ship with
the package (`backend/workflows/templates/`); the tutorial **datasets** are
generated from the [repository](https://github.com/yuchenz93/SynapChart)'s
`scripts/` folder — see
[Getting Started](../getting-started.md#your-first-pipeline-about-5-minutes) for
the setup.

## Worked examples

- **[Theta Phase Precession](theta-phase-precession.md)** — the reference
  end-to-end workflow, block by block.
- **[Tutorial 1](../tutorials/tutorial1.md)** — build a workflow from scratch,
  then package it as a composite block.
- **[Tutorial 2](../tutorials/tutorial2.md)** — batch-process many sessions with
  the Dataset Iterator.
- **[Tutorial 3](../tutorials/tutorial3.md)** — a real-data theta-sequence
  workflow on CRCNS HC-11.
