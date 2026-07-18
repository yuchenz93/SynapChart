# Security & Trust Model

SynapChart is a **local, single-user application**. The backend runs on your own
machine (default `127.0.0.1:8000`) and has the same access to your files and
system as you do. This document explains what that means and how SynapChart
protects you when you open workflows from other people.

## Workflows can contain executable code

A SynapChart workflow is more than a diagram. Blocks execute Python, and a
workflow file can carry that Python with it in two ways:

- **Local blocks** — custom blocks whose source is embedded directly in the
  workflow JSON (`local_blocks`). Their code runs when you **run** the pipeline.
- **Embedded library blocks** — a *packed* workflow (`📦 Pack`) bundles the full
  source of every block it uses (`embedded_blocks`) so it is self-contained.
  This code is registered when the workflow is **loaded with your consent**.

Opening a workflow from an untrusted source is therefore equivalent to running
an unknown script. **Only open workflows from sources you trust.**

## The consent gate

To make that risk explicit rather than silent, opening a workflow that contains
custom code triggers a consent dialog **before any of that code runs**:

1. `POST /api/files/load` is first called *untrusted*. The backend parses and
   migrates the workflow and returns a **code manifest** — the block IDs and
   full source of every custom code block — **without executing anything**.
2. The UI shows you the manifest (each block's source is viewable). You can
   **Cancel** (nothing is loaded and nothing runs) or **Trust & Load**.
3. Only on *Trust & Load* does the backend re-load with `trusted=true` and
   register the embedded code, after which the workflow appears on the canvas.

Because an untrusted load never places the workflow on the canvas, an
un-consented workflow also cannot be run.

Built-in **templates** that ship with SynapChart are considered trusted (they
are part of the installed package) and do not prompt.

## What the gate does *not* cover

- **Running your own workflows.** Once you author or consent to a workflow, its
  blocks run with your permissions. This is by design — that is what the tool is
  for.
- **`pip` dependency installation.** A block may declare pip dependencies that
  are installed into your environment at run time. Review a block's declared
  dependencies before running it.
- **Network exposure.** Running with `--host 0.0.0.0` exposes the server (and
  arbitrary code execution) to your network. Do this only on a trusted network.
- **Cache files.** Cached results are stored as pickle files under
  `.synapchart_cache/`. Do not point SynapChart at a cache directory you did not
  generate yourself.

## Reporting a vulnerability

Please open a private security advisory on the GitHub repository rather than a
public issue.
