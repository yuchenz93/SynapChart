# Composite Blocks

A **composite block** packages an entire workflow into a single reusable node.
Once packaged, it behaves like any other block — drag it from the side panel, wire
it up, and run it — but internally it runs the whole sub-pipeline you built. This
is how you turn a working analysis into something you (and your lab) can reuse
across sessions and projects.

## Why use them

- **Reuse.** Build a pipeline once, then apply it to many datasets without
  rebuilding the graph each time.
- **Abstraction.** Hide a complex 15-block pipeline behind a clean node with a few
  input ports and a few outputs.
- **Sharing.** A composite block's definition is embedded in any workflow that
  uses it, so a saved `.json` opens on a colleague's machine with no extra install
  (subject to the [code-consent gate](../workflows/index.md#saving-loading-and-sharing)).

## Creating a composite block

1. Build and test a normal workflow on the canvas.
2. Click **⊞ Package as block** in the canvas tab bar to open the packaging
   wizard.
3. **Step 1 — Promote inputs.** Choose which internal block parameters (e.g. file
   paths) become **input ports** on the composite's surface, and give each an
   external label. Parameters you don't promote stay fixed inside.
4. **Step 2 — Expose outputs.** Choose which internal output ports become the
   composite's **output ports**, and label them.
5. **Step 3 — Metadata.** Give the block a name, `block_type_id`, category, and
   description.

Click **Save composite block**. It appears in the side panel (typically under a
**Composite** category) and is available in every workflow.

!!! tip "Promote what changes, fix what doesn't"
    Promote the inputs that differ per run (session paths, a direction flag) and
    leave stable analysis parameters baked in. That gives a clean, purpose-built
    node instead of exposing dozens of knobs.

## Using a composite block

Drag it from the side panel onto any canvas and connect its ports like any other
block. At run time it executes its internal pipeline; its promoted inputs feed the
right internal blocks, and its exposed outputs carry the internal results forward.

Composites participate in [smart caching](../workflows/index.md#running-a-workflow)
just like ordinary blocks, and can be nested — a composite may itself contain other
composites.

## Inspecting the internals: Drill in

Click **⊞ Drill in** at the bottom of a composite node to open its internal
workflow in a nested canvas tab. You can read the wiring and even double-click
internal blocks to edit their parameters without leaving the view.

## Walkthrough

[Tutorial 1, Part 4](../tutorials/tutorial1.md#part-4-composite-blocks-and-multi-session-analysis)
packages the theta phase-precession pipeline into a `PhasePrecession` composite
block — promoting three file-path inputs and exposing a correlation output — then
uses two copies of it to analyse two sessions in parallel.
