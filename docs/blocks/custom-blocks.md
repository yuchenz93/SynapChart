# Custom Blocks

Custom blocks are ordinary Python functions decorated with the `@block` pattern and saved in `backend/blocks/user/`. They appear in the block library immediately after a server restart, behave identically to built-in blocks, and can be shared with collaborators as plain `.py` files.

---

## Creating a custom block

### Option 1 — Block wizard (recommended)

1. Click **+ New block** in the block library panel.
2. Fill in the block name, description, input ports, output ports, and parameters in the form.
3. Click **Generate**. SynapChart scaffolds the Python file for you and opens it in the built-in code editor.
4. Write your analysis logic between the `# --- User code start ---` and `# --- User code end ---` comments.
5. Click **Save**. The server hot-reloads the block — it appears in the library instantly.

### Option 2 — Edit the file directly

Create a file in `backend/blocks/user/my_block.py` following this template:

```python
from __future__ import annotations
from blocks.base import BlockBase, PortDefinition, ParameterDefinition
from neurodata.types import NeuroData
import numpy as np


class MyBlock(BlockBase):

    block_type_id = "my_block"        # unique snake_case ID
    display_name  = "My Block"        # shown on the canvas
    category      = "Custom"
    description   = "One sentence describing what this block does."
    is_custom     = True

    inputs = [
        PortDefinition("signal", "NeuroData[raw_signal]", "Input signal."),
    ]
    outputs = [
        PortDefinition("result", "NeuroData[raw_signal]", "Processed output."),
    ]
    parameters = [
        ParameterDefinition("scale", "float", 1.0, "Scaling factor."),
    ]

    def run(self, inputs: dict, parameters: dict) -> dict:
        signal: NeuroData = inputs["signal"]
        scale = float(parameters.get("scale", 1.0))

        return {
            "result": NeuroData(
                data_type="raw_signal",
                array=signal.array * scale,
                sampling_rate=signal.sampling_rate,
                timestamps=signal.timestamps,
            )
        }
```

Restart the SynapChart server (`synapchart`) and the block will appear in the **Custom** category.

!!! tip "What's always in scope inside `run()`"
    `numpy` (as `np`), `NeuroData`, and `Path` are always importable. Any other package must be imported explicitly inside `run()`.

---

## vsRef Channel (example)
`vs_ref_channel`

An auto-generated example block that selects one channel from a multi-channel signal and subtracts a reference channel — a common re-referencing step in LFP preprocessing.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `signal` | Input | `NeuroData[raw_signal]` | Multi-channel signal (N_samples × N_channels) |
| `channel` | Output | `NeuroData[raw_signal]` | Re-referenced single-channel signal (N_samples,) |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `channel_index` | int | `0` | Zero-based index of the channel to extract |
| `ref_channel_index` | int | `1` | Zero-based index of the reference channel |

---

## Tips

- **Block IDs must be unique.** If two files define the same `block_type_id` the second one wins — rename to avoid conflicts.
- **Sharing blocks.** Copy the `.py` file from `backend/blocks/user/` into a collaborator's `user/` folder and restart their server.
- **Dependencies.** If your block requires a non-standard package, add it to `requirements.txt` and import it inside `run()` rather than at the module top level.
- **Type safety.** Connect only compatible port types. The port validator will warn you if types don't match before you run the pipeline.
