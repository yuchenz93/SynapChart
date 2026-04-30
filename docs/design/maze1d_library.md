# Design: `maze1d` — State-Aware 1D Maze Analysis Library

**Status**: Design proposal  
**Scope**: New library, additive — does not overwrite or replace existing blocks  
**Applies to**: Linear (1D) maze recordings, initially targeting CRCNS hc-11 data

---

## Motivation

The current `crcns_hc11_theta_precession` workflow duplicates every analysis node
once per run direction (dir1 / dir2). Adding a second session would require another
full copy of the graph. The root cause is that run direction and session identity
are encoded in the *graph topology* rather than in the *data*.

The `maze1d` library solves this by introducing a **state-aware data model**: a
`NeuroData[states]` object defines named time-interval collections (e.g.
`ec013.527_dir1`, `ec013.527_dir2`), and every analysis block iterates over all
states internally. The workflow graph stays flat regardless of how many sessions
or conditions are analysed.

---

## Scope and boundaries

- This is a **domain-specific library** for 1D linearized maze experiments.
- `direction` as a first-class state attribute is specific to this domain and is
  not a general SynapChart concept.
- The existing block library is **untouched**. `maze1d` is purely additive.
- SynapChart's core (executor, store, block base) requires **no changes**.

---

## Core data structure: `NeuroData[states]`

The states object is stored in `NeuroData.metadata["states"]` as a dictionary:

```python
{
  "<state_name>": {
    "session_id":  str,           # e.g. "ec013.527"
    "direction":   int | None,    # 1 = descending, 2 = ascending, None = undirected
    "intervals":   [(t0, t1), …], # list of (start, end) in seconds
    "metadata":    dict,          # optional extra fields (speed_threshold, etc.)
  },
  …
}
```

### Naming convention

`{session_id}_dir{direction}` for directional states, `{session_id}_{label}` for
undirected states (e.g. `ec013.527_sleep`, `ec013.527_opto`).

### How blocks use states

Every state-aware block:
1. Receives `NeuroData[states]` on a `states` input port
2. Iterates over each state key
3. Slices the raw data arrays to the union of that state's intervals
4. Produces results keyed by state name in `NeuroData.metadata["results"]`

Raw data (LFP, spikes, position) is **loaded once** as a full session array.
States provide the time masks — no re-loading or data duplication.

---

## Block inventory

### New blocks (maze1d-specific)

| Block | Category | Description |
|---|---|---|
| `define_maze_states` | maze1d / States | Wraps `detect_run_laps`; groups laps by direction into states; attaches session_id |
| `merge_states` | maze1d / States | Optional: averages or concatenates selected states into a new synthetic state for mid-pipeline aggregation |

### State-aware analysis blocks (maze1d refactors of existing blocks)

| New block | Replaces | Notes |
|---|---|---|
| `compute_tuning_curves_1d` | `compute_tuning_curve` + `compute_population_tuning_curves` | One tuning curve map per state |
| `detect_place_fields_1d` | `detect_place_fields` | Per-state field boundaries |
| `decode_position_1d` | `bayesian_decoder` | Uses tuning curves from matching state |
| `compute_phase_precession_1d` | `compute_phase_precession` | Reads `direction` from state to flip position axis |
| `compute_theta_sequences_1d` | `compute_theta_sequences` | Per-state sequence stack |

### Visualization blocks

| Block | Description |
|---|---|
| `plot_tuning_curves_1d` | Grid of tuning curves; state selector parameter |
| `plot_decoding_1d` | Decoded posterior heatmap; state selector parameter |
| `plot_phase_precession_1d` | Scatter + r histogram; state selector parameter |
| `plot_theta_sequences_1d` | Sequence heatmap; state selector parameter |

### Upstream blocks (unchanged, state-unaware)

These blocks operate on the full session array and remain as-is in the existing
library. Their outputs are shared across all states:

- All CRCNS loaders (`load_crcns_lfp`, `load_crcns_session`)
- All LFP blocks (`bandpass_filter`, `extract_phase`, `detect_theta_cycles`)
- All behavior blocks (`linearize_position`, `smooth_position`, `compute_speed`, `detect_run_laps`)

---

## `define_maze_states` block detail

**Inputs**
- `laps` — `NeuroData[laps]` from `detect_run_laps`

**Parameters**
- `session_id` — string, e.g. `"ec013.527"` (set manually per session)
- `min_laps` — int, minimum lap count to include a direction (default 3)

**Output: `NeuroData[states]`**

Internally groups laps by direction and collects their `(t_start, t_end)` intervals
into two states: `{session_id}_dir1` and `{session_id}_dir2`.

---

## `merge_states` block detail

Optional, only needed when an aggregated result must feed further analysis
(e.g. cross-session population tuning curve used for decoding).

**Inputs**
- `states` — `NeuroData[states]`
- `results` — any state-indexed `NeuroData`

**Parameters**
- `state_keys` — list of state names to merge
- `new_state_name` — name for the synthetic output state
- `method` — `mean` | `concatenate`

**Output**: new `NeuroData[states]` with the merged state appended.

---

## New workflow: `maze1d_theta_precession`

Functionally identical to `crcns_hc11_theta_precession` but flat and clean.

### Node list (approximate)

```
[Session loading — state-unaware]
n_load_lfp          load_crcns_lfp
n_load_session      load_crcns_session   (spikes + position + laps)

[Behavior preprocessing — state-unaware]
n_linearize         linearize_position
n_smooth            smooth_position
n_speed             compute_speed
n_laps              detect_run_laps

[State definition]
n_states            define_maze_states   ← session_id parameter set here

[LFP preprocessing — state-unaware, computed once]
n_bandpass          bandpass_filter
n_phase             extract_phase
n_theta_cycles      detect_theta_cycles

[State-aware analysis — each block iterates over all states internally]
n_tuning            compute_tuning_curves_1d
n_fields            detect_place_fields_1d
n_decode            decode_position_1d
n_precession        compute_phase_precession_1d
n_sequences         compute_theta_sequences_1d

[Visualization — state selector parameter picks which states to show]
n_plot_tuning       plot_tuning_curves_1d
n_plot_decode       plot_decoding_1d
n_plot_precession   plot_phase_precession_1d
n_plot_sequences    plot_theta_sequences_1d
```

Node count: ~16 vs ~30 in the current workflow. Adding a second session adds
exactly 2 nodes: one more `load_crcns_session` (or reuse with different params)
and one more `define_maze_states` with a different `session_id`. All analysis
and visualization nodes remain shared.

---

## State pairing contract

When `decode_position_1d` receives tuning curves and a states object, it pairs
them by state key: laps from `ec013.527_dir1` are decoded using the tuning curve
computed from `ec013.527_dir1`. This is implicit — no explicit wiring needed.

The same pairing applies to phase precession (position axis orientation comes
from `state.direction`) and theta sequences (only spikes/LFP from matching
intervals are used).

---

## Implementation order

1. Define `NeuroData[states]` schema and document the convention
2. Implement `define_maze_states`
3. Implement `compute_tuning_curves_1d` (most other blocks depend on it)
4. Implement `detect_place_fields_1d`
5. Implement `decode_position_1d`
6. Implement `compute_phase_precession_1d`
7. Implement `compute_theta_sequences_1d`
8. Implement visualization blocks
9. Build `maze1d_theta_precession` workflow template
10. Validate parity with `crcns_hc11_theta_precession` output
