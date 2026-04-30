# Common Issues When Building Blocks and Workflows

A running record of errors that have appeared more than once, along with the root cause and the fix.
Check this file first when a block or workflow fails to run.

---

## 1. `NeuroData.__init__() missing 1 required positional argument: 'array'`

**When it appears:** Any block that constructs and returns a `NeuroData` object without passing `array`.

**Root cause:** `NeuroData` is a `@dataclass`.  `data_type` and `array` are both *positional* (non-default) fields.  Omitting `array` raises a `TypeError` at instantiation, which surfaces as a pipeline error message.

**Fix:**

```python
# WRONG — missing array
return {"my_output": NeuroData(data_type="foo", metadata={...})}

# CORRECT — always pass array, even for plot/summary blocks
return {"my_output": NeuroData(
    data_type = "foo",
    array     = np.array([0.0]),   # dummy scalar is fine for non-array outputs
    metadata  = {...},
)}
```

**Pattern for visualization / summary blocks:** pass a small 1-D array containing the key scalar result (e.g. `np.array([r_run, r_rest])`) so the output is at least inspectable.

---

## 2. `KeyError: 'timestamps'` when reading decoded posteriors

**When it appears:** Blocks that consume `NeuroData[decoded_1d]` from `decode_position_1d` and try to access time bins.

**Root cause:** `decode_position_1d` stores the bin-centre timestamps as `NeuroData.timestamps` (the dataclass field), **not** inside `metadata["timestamps"]`.

**Fix:**

```python
# WRONG
ts_decode = np.asarray(dc.metadata["timestamps"])

# CORRECT
ts_decode = np.asarray(dc.timestamps)          # NeuroData.timestamps field
```

**General rule:** always check whether a value lives on the `NeuroData` object itself (`array`, `timestamps`, `sampling_rate`, `channel_names`) or inside `metadata` before accessing it.

---

## 3. Python 3.8 type hint syntax error (`dict[str, Any]` in function signatures)

**When it appears:** A new block loads correctly on Python ≥ 3.9 but raises `TypeError: 'type' object is not subscriptable` on the server (Python 3.8).

**Root cause:** Built-in generics like `dict[str, Any]`, `list[str]`, `tuple[int, ...]` are only valid as annotations from Python 3.9+.  The SynapChart server runs Python 3.8.

**Fix:** Add `from __future__ import annotations` as the **first import** in every block file.

```python
# MUST be the very first import — before everything else
from __future__ import annotations

from typing import Any
import numpy as np
...
```

This makes all annotations strings at parse time, so 3.8 never evaluates them.

---

## 4. Fisher's exact test direction for "POST > PRE" plasticity

**When it appears:** `fisher_exact` returns `p ≈ 1` when testing whether replay rate in POST sleep is higher than in PRE sleep.

**Root cause:** `alternative="greater"` in scipy tests whether the **odds ratio > 1**, i.e. the *first row* rate is higher than the *second row* rate.  If the contingency table is arranged as `[[PRE_sig, PRE_ns], [POST_sig, POST_ns]]`, this tests PRE > POST — the opposite of what's wanted.

**Fix:** use `alternative="less"` to test OR < 1, which means the first-row rate is *lower* than the second-row rate (POST > PRE).

```python
table = [
    [n_pre_sig,  n_pre_ns],   # row 0 = PRE
    [n_post_sig, n_post_ns],  # row 1 = POST
]
_, pval = fisher_exact(table, alternative="less")
# "less" → OR < 1 → PRE rate < POST rate → POST rate > PRE rate ✓
```

---

## 5. Parameter default must be updated in **both** places

**When it appears:** A parameter's effective default stays at the old value even after editing the `ParameterDefinition`.

**Root cause:** A block's default value appears in two independent places:

1. `ParameterDefinition("n_shuffles", "int", 500, ...)` — displayed in the UI and saved to the workflow JSON.
2. `parameters.get("n_shuffles", 100)` — the runtime fallback when the key is absent from the dict.

If only one is updated, the other takes over depending on whether the workflow JSON was saved before or after the change.

**Fix:** always grep for the parameter name and update **both** occurrences.

```python
# ParameterDefinition — sets UI default and what gets written to workflow JSON
ParameterDefinition("n_shuffles", "int", 500, "Number of shuffles.")

# parameters.get fallback — must match
n_shuffles = int(parameters.get("n_shuffles", 500))   # same default ← easy to forget
```

---

## 6. Library refresh vs. browser reload

**When it appears:** After adding or editing blocks in `~/.synapchart/blocklibrary/`, the frontend still shows the old block definitions or shows blocks as disconnected.

**Root cause:** Two independent caches exist:

| Cache | Reset by |
|---|---|
| Backend block registry | `POST /api/libraries/refresh` |
| Frontend `blockIndex` (Zustand store) | Browser tab reload |

`POST /api/libraries/refresh` updates the server but the frontend keeps its stale copy.  Workflows loaded *before* the reload still work (they resolve blocks at runtime), but newly dragged blocks or port definitions may be wrong.

**Fix (standard workflow after editing any block):**

```bash
curl -X POST http://localhost:8000/api/libraries/refresh
# then reload the browser tab
```

The `/api/libraries/refresh` call is safe to run from the terminal at any time without restarting the server.

---

## 7. `decode_waking_rest_replay` must reuse cached upstream outputs

**When it appears:** Running a workflow step-by-step, the `decode_waking_rest_replay` node errors with a missing-input message even though upstream nodes completed successfully.

**Root cause:** The step endpoint (`POST /api/pipeline/step`) reads upstream outputs from the checkpoint cache.  If upstream nodes were run in a *different* workflow run (different cache key), or if the cache was cleared, the downstream node sees no inputs.

**Fix:** use `POST /api/pipeline/run-from-cache` rather than individual step calls when re-running only downstream nodes after fixing a bug.  Only clear the cache for the specific node being fixed:

```bash
curl -X POST http://localhost:8000/api/pipeline/clear-cache \
     -H "Content-Type: application/json" \
     -d '{"node_id": "n_rest_neural_dist"}'
```

---

## 8. `two_d_location` is in **metres** — multiply by 100 for cm

**When it appears:** 2D place maps appear at ~100× the wrong scale (tiny dot cluster in a corner, or absurd bin counts).

**Root cause:** CRCNS hc-11 stores the 2D position in `sessInfo.Position.TwoDLocation` in **metres**.  The 1D linearized position (`sessInfo.Position.OnTrack`) is loaded separately and normalised to cm by the `load_crcns_session` block.  But `two_d_location` is stored raw in metadata and must be converted before use.

**Fix:**

```python
pos_2d_cm = np.asarray(pos_nd.metadata["two_d_location"]) * 100.0   # m → cm
```

---

## 9. Block not appearing in the block library after adding it

**When it appears:** A new `.py` file is added to a library's `blocks/` directory but the block does not show up in the side panel after refresh.

**Common causes and fixes:**

| Cause | Fix |
|---|---|
| `class_type_id` contains a dot or dash | Use only `snake_case` (letters, digits, underscores) |
| Class does not inherit from `BlockBase` | Add `class MyBlock(BlockBase):` |
| Syntax error in the file | Run `python -c "import my_block"` from the blocks directory to surface it |
| `library.json` `id` field does not match the directory name | They don't have to match, but the `id` must be unique across all loaded libraries |
| Server not restarted / refresh not called | `POST /api/libraries/refresh` then browser reload |

After fixing, confirm with:
```bash
curl http://localhost:8000/api/libraries/<library_id>
```
The response's `categories` list should include the new block.

---

## 10. Visualization blocks produce no output in the frontend (`plt.show()` does nothing on a server)

**When it appears:** A plot block runs without error but no figure appears in the frontend.

**Root cause:** The executor emits figures to the frontend via a `_viz` WebSocket message only when the block's return dict contains `"_viz": {"image_b64": "data:image/png;base64,..."}`.  Calling `plt.show()` on the server is a no-op; the figure is drawn in memory and then discarded.

**Fix:** use `save_and_encode` from `blocks.visualization` and return `_viz`:

```python
from blocks.visualization import save_and_encode
# ...
fig, ax = plt.subplots(...)
# ... draw the figure ...
viz = save_and_encode(fig, save_path, show_on_run)   # closes fig, returns {"image_b64": ...}
return {
    "my_output": NeuroData(...),
    "_viz": viz,              # executor reads this and broadcasts viz_result
}
```

`save_and_encode` calls `matplotlib.use("Agg")` at import time (headless), saves to disk if `save_path` is non-empty, encodes to base64 PNG if `show_on_run` is True, and closes the figure.  Do **not** call `plt.show()` or `plt.close()` separately.

---

## 11. Significance counting: frames × directions vs. unique frames

**When it appears:** A replay significance ratio is suspiciously low (e.g. 5% when directional bars show ~30%).

**Root cause:** If two directions are decoded independently, each frame contributes **two** independent representations.  Dividing `n_sig` by `n_unique_frames` (instead of `n_frames × n_directions`) inflates the denominator and underreports the ratio.

**Fix:** count denominator as total representations, not unique frames:

```python
n_representations = len(results)     # already = n_frames × n_directions
n_sig = sum(1 for r in results if r["is_sig"])
sig_ratio = n_sig / n_representations
```
