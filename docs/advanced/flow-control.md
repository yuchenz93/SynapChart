# Flow Control Blocks

Flow control blocks drive batch execution and inject constant values. They are handled specially by the execution engine.

---

## Dataset Iterator
`dataset_iterator`

Reads a CSV file row by row and drives one full downstream execution per row. The executor detects this block and loops over rows, injecting column values as synthetic output port values for each iteration.

Output ports are **dynamic**: one port per entry in `column_mappings`, resolved at runtime.

!!! info "Executor handling"
    `dataset_iterator` is never executed via `run()`. The execution engine handles it directly. Pair it with a `collect_results` block to accumulate outputs across iterations.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| *(dynamic)* | Output | `str` | One port per column mapping; names and types are defined by `column_mappings` |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `csv_path` | str | `""` | Path to the dataset CSV file |
| `column_mappings` | str | `""` | JSON mapping output port names to CSV column names, e.g. `{"lfp_path": "lfp_file"}` |
| `skip_header` | bool | `true` | Whether the first row is a header row |
| `session_id_col` | str | `""` | Optional column name to use as the session label in logs |

---

## Collect Results
`collect_results`

Accumulates outputs from repeated iterations into a single stacked array. In a batch context (driven by `dataset_iterator`) the executor bypasses `run()` and calls `finalize()` once all iterations are complete.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `item` | Input | `NeuroData[any]` | One result per iteration |
| `collection` | Output | `NeuroData[any]` | Stacked array across all iterations (n_iterations × ...) |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `axis` | int | `0` | Axis along which to stack results |
| `keep_metadata_from` | enum | `first` | Which iteration's metadata to carry forward: `first` or `last` |

---

## String Constant
`string_constant`

Outputs a fixed string value. Useful for connecting a file path into a composite block's string input port without needing a CSV iterator.

**Ports**

| Port | Direction | Type | Description |
|------|-----------|------|-------------|
| `value` | Output | `str` | The constant string value |

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `value` | str | `""` | The string to output |

---

## Batch processing pattern

A typical batch workflow looks like this:

```
dataset_iterator
    │  (lfp_path, spikes_path per row)
    ▼
[your analysis blocks]
    │  (one result per session)
    ▼
collect_results
    │  (stacked array: n_sessions × ...)
    ▼
[aggregate visualization or export]
```

The iterator drives one complete execution of all downstream blocks per CSV row. `collect_results` stacks the outputs into a single array for aggregate analysis.
