"""Pipeline execution engine for SynapChart."""


from __future__ import annotations

import asyncio
import builtins
import contextvars
import csv
import importlib.util
import json
import queue
import re
import sys
from pathlib import Path
from typing import AsyncGenerator

from core.graph import topological_sort, build_downstream_map, all_descendants
from core.checkpoint import _make_key, has_cache, load_cache, save_cache
from core.block_registry import get_block
from core.validator import validate_workflow
from blocks.base import CompositeBlockDefinition


def _log(level: str, node_id: str | None, message: str, status: str | None = None, **extra) -> dict:
    """Construct a log message dict matching the WebSocket log schema."""
    msg = {"level": level, "node_id": node_id, "message": message}
    if status is not None:
        msg["status"] = status
    msg.update(extra)
    return msg


# ── disp() — in-app console print for block code ─────────────────────────────
# Each node execution sets this ContextVar to a fresh SimpleQueue before
# dispatching to run_in_executor.  Thread-pool workers inherit the caller's
# context (Python 3.7+), so block code running in the thread sees the same
# queue.  After run_in_executor returns, the executor drains the queue and
# emits each message as a log dict.

_disp_queue: contextvars.ContextVar[queue.SimpleQueue | None] = \
    contextvars.ContextVar("_disp_queue", default=None)


def _disp(value) -> None:
    """Print *value* to the SynapChart in-app console during block execution.

    Falls back to the standard ``print()`` builtin when called outside an
    active execution context (e.g. during unit tests).
    """
    q = _disp_queue.get(None)
    if q is not None:
        q.put(str(value))
    else:
        builtins.__dict__["_original_print"](value)


# Inject disp() into builtins so every block module can call it without an
# explicit import.  Store the original print for the fallback above.
builtins.__dict__.setdefault("_original_print", print)
builtins.disp = _disp  # type: ignore[attr-defined]


def detect_iterator_structure(
    nodes: dict[str, dict], edges: list[dict]
) -> tuple[str | None, list[str], list[str], list[str], list[str]]:
    """Identify iterator/collect_results nodes and split the graph into phases.

    Args:
        nodes: Mapping of node_id -> node dict.
        edges: List of workflow edge dicts.

    Returns:
        Tuple of:
            iterator_node_id  — id of the dataset_iterator node, or None
            pre_loop_nodes    — ordered list of node_ids that run before the loop
            loop_nodes        — ordered list of node_ids that run each iteration
                                (includes the iterator itself and all descendants
                                 up to but not including collect_results outputs)
            collect_node_ids  — ids of all collect_results nodes in the loop
            post_loop_nodes   — ordered list of node_ids that run after the loop
    """
    # Find the iterator node
    iterator_node_id: str | None = None
    for nid, node in nodes.items():
        if node.get("block_type_id") == "dataset_iterator":
            iterator_node_id = nid
            break

    if iterator_node_id is None:
        # No iterator — all nodes run once, nothing special
        all_ids = list(nodes.keys())
        try:
            ordered = topological_sort(list(nodes.values()), edges)
        except ValueError:
            ordered = all_ids
        return None, ordered, [], [], []

    downstream = build_downstream_map(edges)

    # Everything reachable from the iterator (including itself) is in the loop
    loop_set: set[str] = {iterator_node_id} | all_descendants(iterator_node_id, downstream)

    # collect_results nodes within the loop
    collect_node_ids: list[str] = [
        nid for nid in loop_set
        if nodes[nid].get("block_type_id") == "collect_results"
    ]

    # Post-loop: descendants of collect_results nodes
    # These are NOT part of the loop even though they are reachable from the iterator
    post_set: set[str] = set()
    for cnid in collect_node_ids:
        post_set |= all_descendants(cnid, downstream)
    # Remove post-loop nodes from the loop set so they run only once after the loop
    loop_set -= post_set

    # Pre-loop: everything else (no path from or to the iterator subgraph)
    pre_set = set(nodes.keys()) - loop_set - post_set

    # Topologically sort each partition using the full edge list
    node_list = list(nodes.values())
    try:
        full_order = topological_sort(node_list, edges)
    except ValueError:
        full_order = list(nodes.keys())

    pre_loop_nodes  = [nid for nid in full_order if nid in pre_set]
    loop_nodes      = [nid for nid in full_order if nid in loop_set]
    post_loop_nodes = [nid for nid in full_order if nid in post_set]

    return iterator_node_id, pre_loop_nodes, loop_nodes, collect_node_ids, post_loop_nodes


def _read_csv_rows(csv_path: str, parameters: dict) -> list[dict]:
    """Read all data rows from the CSV described by the iterator's parameters.

    Args:
        csv_path:   Absolute or relative path to the CSV file.
        parameters: The dataset_iterator node's parameter dict.

    Returns:
        List of row dicts mapping CSV column name -> cell value string.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError:        If column_mappings cannot be parsed.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"dataset_iterator: CSV file not found: {csv_path}")

    skip_header = bool(parameters.get("skip_header", True))

    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header: list[str] | None = None
        for i, raw_row in enumerate(reader):
            # Skip empty rows
            if not any(cell.strip() for cell in raw_row):
                continue
            if i == 0 and skip_header:
                header = [c.strip() for c in raw_row]
                continue
            if header is None:
                # No header row — use numeric string keys
                rows.append({str(j): val.strip() for j, val in enumerate(raw_row)})
            else:
                rows.append(
                    {header[j]: val.strip() for j, val in enumerate(raw_row) if j < len(header)}
                )
    return rows


def _row_to_outputs(row: dict, column_mappings: dict) -> dict:
    """Convert a CSV row dict into iterator output port values.

    Args:
        row:             Mapping of CSV column name -> value string.
        column_mappings: Mapping of output port_id -> CSV column name.

    Returns:
        Mapping of port_id -> string value for that iteration.
    """
    return {
        port_id: row.get(col_name, "")
        for port_id, col_name in column_mappings.items()
    }


async def _ensure_dependencies(block, node_id: str) -> AsyncGenerator[dict, None]:
    """Check and install any pip dependencies declared on a block.

    Reads ``block._dependencies`` (a list of pip requirement specs, e.g.
    ``["elephant", "mne>=1.6"]``), checks each with
    ``importlib.util.find_spec``, and installs missing ones via
    ``pip install`` before the block runs.

    Args:
        block:   The block instance to check.
        node_id: Used for log message attribution.

    Yields:
        Log message dicts.  An ``{"status": "error"}`` message signals
        installation failure — callers should abort execution.
    """
    deps: list[str] = list(getattr(block, "_dependencies", []) or [])
    if not deps:
        return

    yield _log("info", node_id, "Checking dependencies…", status="running")

    for dep in deps:
        # Derive the importable module name by stripping version/extras specifiers
        # and normalising dashes to underscores (best-effort; common packages match).
        module_name = re.split(r"[><=!;\[@\s]", dep.strip())[0].replace("-", "_").lower()

        if importlib.util.find_spec(module_name) is not None:
            continue  # already importable — skip

        yield _log("info", node_id, f"Installing: {dep}", status="running")

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", dep,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout_bytes, _ = await proc.communicate()
        except Exception as exc:  # noqa: BLE001
            yield _log(
                "error", node_id,
                f"Could not launch pip to install '{dep}': {exc}",
                status="error",
            )
            return

        if proc.returncode != 0:
            output = stdout_bytes.decode(errors="replace").strip()
            yield _log(
                "error", node_id,
                f"Failed to install '{dep}':\n{output}",
                status="error",
            )
            return

        # Invalidate the import cache so the freshly installed package is visible
        importlib.invalidate_caches()
        yield _log("info", node_id, f"'{dep}' installed successfully.", status="running")


class PipelineExecutor:
    """Executes a SynapChart workflow.

    Supports three modes:
    - Full run  (use_cache=False): all nodes execute from scratch.
    - Cached run (use_cache=True): nodes with valid checkpoints are skipped.
    - Step: a single named node executes; its inputs must be cached.

    Usage::

        executor = PipelineExecutor(workflow)
        async for log_msg in executor.run(use_cache=True):
            await broadcast(log_msg)   # stream to WebSocket clients
    """

    def __init__(
        self,
        workflow: dict,
        injected_inputs: dict | None = None,
        injected_params: dict | None = None,
        parent_run_id: str | None = None,
    ) -> None:
        self.workflow = workflow
        self.nodes: dict[str, dict] = {
            n["node_id"]: n for n in workflow.get("nodes", [])
        }
        self.edges: list[dict] = workflow.get("edges", [])
        self._outputs: dict[str, dict] = {}        # node_id -> {port_id -> value}
        self._cache_keys: dict[str, str] = {}      # node_id -> cache_key
        self._stop_requested: bool = False
        # For nested (composite) execution: pre-seeded data-port input values
        self._injected_inputs: dict = injected_inputs or {}  # node_id -> {port_id -> value}
        # For promoted parameters: parameter value overrides per node
        self._injected_params: dict = injected_params or {}  # node_id -> {param_name -> value}
        self._parent_run_id: str | None = parent_run_id
        # Public: callers can read final outputs after run() completes
        self.outputs: dict[str, dict] = self._outputs

    def stop(self) -> None:
        """Signal the executor to stop after the current node finishes."""
        self._stop_requested = True

    # ------------------------------------------------------------------
    # Public run interface
    # ------------------------------------------------------------------

    async def run(self, use_cache: bool = True) -> AsyncGenerator[dict, None]:
        """Execute all nodes in topological order.

        Automatically detects ``dataset_iterator`` nodes and switches to
        batch execution mode, running the loop subgraph once per CSV row.

        Args:
            use_cache: If True, nodes with valid checkpoints are skipped.

        Yields:
            Log message dicts: ``{"level", "node_id", "message", "status?"}``
        """
        # Ensure local blocks embedded in the workflow are registered before
        # validation.  This is a no-op when they are already present (e.g. the
        # frontend called /api/blocks/register-local beforehand), but is essential
        # after a server restart because the registry starts empty and local blocks
        # only live in the workflow JSON — not on disk.
        local_blocks = self.workflow.get("local_blocks", [])
        if local_blocks:
            from api.blocks import _register_local_block_definitions
            _register_local_block_definitions(local_blocks)

        # For packed workflows: ensure embedded blocks for missing libraries are
        # registered.  The load path already does this, but if the server was
        # restarted between load and run the dynamic registrations are lost.
        if self.workflow.get("packed"):
            embedded = self.workflow.get("embedded_blocks", {})
            if embedded:
                from core.library_registry import _libraries
                missing_lib_ids = {
                    lib["id"]
                    for lib in self.workflow.get("libraries", [])
                    if isinstance(lib, dict) and lib.get("id") not in _libraries
                }
                if missing_lib_ids:
                    from api.files import _register_embedded_blocks
                    _register_embedded_blocks(embedded, missing_lib_ids)

        errors = validate_workflow(self.workflow)
        if errors:
            for e in errors:
                yield _log("error", None, e)
            return

        # Detect iterator structure
        try:
            (
                iterator_node_id,
                pre_loop_nodes,
                loop_nodes,
                collect_node_ids,
                post_loop_nodes,
            ) = detect_iterator_structure(self.nodes, self.edges)
        except ValueError as exc:
            yield _log("error", None, str(exc))
            return

        if iterator_node_id is not None:
            # Batch mode
            all_node_count = len(pre_loop_nodes) + len(loop_nodes) + len(post_loop_nodes)
            yield _log(
                "info", None,
                f"Starting batch pipeline ({all_node_count} nodes, iterator detected).",
                status="plan",
                order=pre_loop_nodes + loop_nodes + post_loop_nodes,
            )
            async for msg in self._run_batch(
                iterator_node_id, pre_loop_nodes, loop_nodes,
                collect_node_ids, post_loop_nodes, use_cache,
            ):
                yield msg
            return

        # Normal (non-batch) mode
        order = pre_loop_nodes  # detect_iterator returns all nodes here when no iterator
        yield _log("info", None, f"Starting pipeline ({len(order)} nodes).",
                   status="plan", order=order)

        for node_id in order:
            if self._stop_requested:
                yield _log("info", None, "Pipeline stopped by user.", status="stopped")
                return
            async for msg in self._execute_node(node_id, use_cache):
                yield msg

        yield _log("info", None, "Pipeline complete.")

    async def step(self, node_id: str) -> AsyncGenerator[dict, None]:
        """Execute a single node, loading upstream results from cache.

        All ancestors are loaded in topological order so that each node's
        cache key can be derived from its predecessors' cache keys (matching
        the keys stored during the original full run).

        Args:
            node_id: The node to execute.

        Yields:
            Log message dicts.
        """
        if node_id not in self.nodes:
            yield _log("error", None, f"Node '{node_id}' not found in workflow.",
                       status="error")
            return

        # Emit a plan for one node so the frontend resets viz/progress panels
        yield _log("info", None, f"Stepping node '{node_id}'.",
                   status="plan", order=[node_id])

        # Build a full predecessor map for ancestor traversal
        predecessors_map: dict[str, set[str]] = {nid: set() for nid in self.nodes}
        for edge in self.edges:
            predecessors_map[edge["target_node_id"]].add(edge["source_node_id"])

        # BFS to collect all ancestors of node_id
        ancestors: set[str] = set()
        to_visit: list[str] = list(predecessors_map.get(node_id, set()))
        while to_visit:
            pred = to_visit.pop()
            if pred not in ancestors:
                ancestors.add(pred)
                to_visit.extend(predecessors_map.get(pred, set()))

        # Topologically sort the whole graph so we visit ancestors source-first.
        # This ensures each ancestor's cache key is computed with its own
        # predecessors' cache keys already populated in self._cache_keys.
        try:
            full_order = topological_sort(list(self.nodes.values()), self.edges)
        except ValueError as exc:
            yield _log("error", None, str(exc), status="error")
            return

        for nid in full_order:
            if nid not in ancestors or nid in self._outputs:
                continue
            anc_node = self.nodes[nid]
            input_keys = self._get_input_cache_keys(nid)
            key = _make_key(
                nid,
                anc_node["block_type_id"],
                anc_node.get("parameters", {}),
                input_keys,
            )
            if has_cache(key):
                self._outputs[nid] = load_cache(key)
                self._cache_keys[nid] = key
            else:
                yield _log(
                    "error", None,
                    f"Cannot step: upstream node '{nid}' has no cached result. "
                    "Run the full pipeline first.",
                    status="error",
                )
                return

        async for msg in self._execute_node(node_id, use_cache=False):
            yield msg

    # ------------------------------------------------------------------
    # Batch execution
    # ------------------------------------------------------------------

    async def _run_batch(
        self,
        iterator_node_id: str,
        pre_loop_nodes: list[str],
        loop_nodes: list[str],
        collect_node_ids: list[str],
        post_loop_nodes: list[str],
        use_cache: bool,
    ) -> AsyncGenerator[dict, None]:
        """Execute a batch workflow driven by a dataset_iterator node.

        Phase 1 — pre-loop nodes run once.
        Phase 2 — loop nodes run once per CSV row; collect_results nodes are
                   skipped during the loop and their inputs accumulated instead.
        Phase 3 — collect_results nodes are finalized; post-loop nodes run once.

        Args:
            iterator_node_id: Node id of the dataset_iterator.
            pre_loop_nodes:   Ordered node ids to run before the loop.
            loop_nodes:       Ordered node ids to run on each iteration
                              (includes the iterator itself).
            collect_node_ids: Node ids of collect_results nodes in the loop.
            post_loop_nodes:  Ordered node ids to run after the loop.
            use_cache:        Whether to use per-iteration checkpoints.

        Yields:
            Log message dicts.
        """
        # --- Phase 1: pre-loop ---
        for node_id in pre_loop_nodes:
            if self._stop_requested:
                yield _log("info", None, "Pipeline stopped by user.", status="stopped")
                return
            async for msg in self._execute_node(node_id, use_cache):
                yield msg

        # --- Read CSV rows ---
        iter_node = self.nodes[iterator_node_id]
        iter_params = {
            **iter_node.get("parameters", {}),
            **self._injected_params.get(iterator_node_id, {}),
        }
        csv_path = iter_params.get("csv_path", "")
        try:
            col_mappings_raw = iter_params.get("column_mappings", "") or "{}"
            column_mappings: dict = json.loads(col_mappings_raw) if col_mappings_raw.strip() else {}
        except json.JSONDecodeError as exc:
            yield _log(
                "error", iterator_node_id,
                f"dataset_iterator: invalid column_mappings JSON — {exc}",
                status="error",
            )
            return

        try:
            rows = _read_csv_rows(csv_path, iter_params)
        except (FileNotFoundError, ValueError) as exc:
            yield _log("error", iterator_node_id, str(exc), status="error")
            return

        n_rows = len(rows)
        session_id_col = iter_params.get("session_id_col", "")

        yield _log(
            "info", iterator_node_id,
            f"Starting batch: {n_rows} session{'s' if n_rows != 1 else ''}.",
            status="batch_start",
            total=n_rows,
        )

        # Accumulator: collect_node_id -> list of per-iteration input values
        batch_items: dict[str, list] = {cnid: [] for cnid in collect_node_ids}

        # --- Phase 2: loop ---
        collect_set = set(collect_node_ids)

        for i, row in enumerate(rows):
            if self._stop_requested:
                yield _log("info", None, "Pipeline stopped by user.", status="stopped")
                return

            session_label = row.get(session_id_col, str(i + 1)) if session_id_col else str(i + 1)
            yield _log(
                "info", iterator_node_id,
                f"Session {i + 1}/{n_rows}: {session_label}",
                status="batch_progress",
                current=i + 1,
                total=n_rows,
            )

            # Inject row outputs as the iterator node's outputs for this iteration
            row_outputs = _row_to_outputs(row, column_mappings)
            self._outputs[iterator_node_id] = row_outputs

            for node_id in loop_nodes:
                if node_id == iterator_node_id:
                    continue  # already handled above
                if node_id in collect_set:
                    # Accumulate rather than execute
                    inputs = self._collect_inputs(node_id)
                    item = inputs.get("item")
                    if item is None:
                        yield _log(
                            "error", node_id,
                            f"collect_results: no 'item' input on iteration {i + 1}.",
                            status="error",
                        )
                        return
                    batch_items[node_id].append(item)
                    yield _log(
                        "info", node_id,
                        f"Collected {i + 1}/{n_rows}.",
                        status="collecting",
                        current=i + 1,
                        total=n_rows,
                    )
                    continue

                # Per-iteration cache key includes the iteration index
                async for msg in self._execute_node_iter(node_id, use_cache, i):
                    yield msg

        yield _log(
            "info", iterator_node_id,
            f"Batch complete. {n_rows}/{n_rows} sessions processed.",
            status="batch_done",
            total=n_rows,
        )

        # --- Finalize collect_results nodes ---
        from blocks.flow_control.collect_results import CollectResults

        for cnid in collect_node_ids:
            items = batch_items[cnid]
            c_node = self.nodes[cnid]
            c_params = {
                **c_node.get("parameters", {}),
                **self._injected_params.get(cnid, {}),
            }
            axis = int(c_params.get("axis", 0))
            keep_metadata_from = str(c_params.get("keep_metadata_from", "first"))
            try:
                outputs = CollectResults.finalize(items, axis, keep_metadata_from)
            except ValueError as exc:
                yield _log("error", cnid, str(exc), status="error")
                return
            self._outputs[cnid] = outputs
            # Cache the finalized collection
            input_keys = self._get_input_cache_keys(cnid)
            cache_key = _make_key(cnid, "collect_results", c_params, input_keys)
            self._cache_keys[cnid] = cache_key
            save_cache(cache_key, outputs)
            yield _log("info", cnid, "Collection finalized.", status="done")

        # --- Phase 3: post-loop ---
        for node_id in post_loop_nodes:
            if self._stop_requested:
                yield _log("info", None, "Pipeline stopped by user.", status="stopped")
                return
            async for msg in self._execute_node(node_id, use_cache):
                yield msg

        yield _log("info", None, "Pipeline complete.")

    async def _execute_node_iter(
        self, node_id: str, use_cache: bool, iteration: int
    ) -> AsyncGenerator[dict, None]:
        """Execute a single loop-subgraph node with per-iteration cache namespacing.

        Identical to _execute_node but injects ``_iter_`` into the parameter
        dict used for cache key computation so each iteration gets its own
        checkpoint slot.

        Args:
            node_id:   Node to execute.
            use_cache: Whether to check for a cached result.
            iteration: Zero-based iteration index.

        Yields:
            Log message dicts.
        """
        node = self.nodes[node_id]
        block_type_id = node["block_type_id"]
        parameters = {
            **node.get("parameters", {}),
            **self._injected_params.get(node_id, {}),
        }
        # Namespace the cache key per iteration
        cache_params = {**parameters, "_iter_": iteration}

        input_keys = self._get_input_cache_keys(node_id)
        cache_key = _make_key(node_id, block_type_id, cache_params, input_keys)
        self._cache_keys[node_id] = cache_key

        # --- Cache hit ---
        if use_cache and has_cache(cache_key):
            self._outputs[node_id] = load_cache(cache_key)
            yield _log("info", node_id, "Loaded from cache.", status="cached")
            viz = self._outputs[node_id].get("_viz", {})
            if viz.get("image_b64"):
                yield _log("info", node_id, "Visualization ready.",
                           status="viz_result", image_b64=viz["image_b64"])
            return

        # --- Execute ---
        yield _log("info", node_id, "Running...", status="running")

        try:
            block = get_block(block_type_id)
        except KeyError:
            yield _log(
                "error", node_id,
                f"Block type '{block_type_id}' is not registered.",
                status="error",
            )
            return

        inputs = self._collect_inputs(node_id)

        # --- Check / install declared pip dependencies ---
        dep_failed = False
        async for msg in _ensure_dependencies(block, node_id):
            yield msg
            if msg.get("status") == "error":
                dep_failed = True
        if dep_failed:
            return

        if isinstance(block, CompositeBlockDefinition):
            async for msg in self._execute_composite(
                node_id, block, inputs, parameters, use_cache
            ):
                yield msg
            save_cache(cache_key, self._outputs.get(node_id, {}))
            yield _log("info", node_id, "Done.", status="done")
            return

        disp_q: queue.SimpleQueue = queue.SimpleQueue()
        token = _disp_queue.set(disp_q)
        exc_caught: Exception | None = None
        try:
            loop = asyncio.get_running_loop()
            # Copy context explicitly so _disp_queue ContextVar is visible in the thread (Python < 3.9 compat).
            ctx = contextvars.copy_context()
            outputs = await loop.run_in_executor(None, ctx.run, block.run, inputs, parameters)
        except Exception as exc:  # noqa: BLE001
            exc_caught = exc
        finally:
            _disp_queue.reset(token)

        while not disp_q.empty():
            yield _log("info", node_id, disp_q.get_nowait(), status="disp")

        if exc_caught is not None:
            yield _log("error", node_id, str(exc_caught), status="error")
            return

        self._outputs[node_id] = outputs
        save_cache(cache_key, outputs)
        yield _log("info", node_id, "Done.", status="done")
        viz = outputs.get("_viz", {})
        if viz.get("image_b64"):
            yield _log("info", node_id, "Visualization ready.",
                       status="viz_result", image_b64=viz["image_b64"])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute_node(
        self, node_id: str, use_cache: bool
    ) -> AsyncGenerator[dict, None]:
        """Execute or cache-load a single node and store its outputs.

        Args:
            node_id:   Node to process.
            use_cache: Whether to check for a valid checkpoint first.

        Yields:
            Log message dicts.
        """
        node = self.nodes[node_id]
        block_type_id = node["block_type_id"]
        parameters = {**node.get("parameters", {}), **self._injected_params.get(node_id, {})}

        input_keys = self._get_input_cache_keys(node_id)
        cache_key = _make_key(node_id, block_type_id, parameters, input_keys)
        self._cache_keys[node_id] = cache_key

        # --- Cache hit ---
        if use_cache and has_cache(cache_key):
            self._outputs[node_id] = load_cache(cache_key)
            yield _log("info", node_id, "Loaded from cache.", status="cached")
            # Re-broadcast any visualization produced by this block
            viz = self._outputs[node_id].get("_viz", {})
            if viz.get("image_b64"):
                yield _log("info", node_id, "Visualization ready.",
                           status="viz_result", image_b64=viz["image_b64"])
            return

        # --- Execute ---
        yield _log("info", node_id, "Running...", status="running")

        try:
            block = get_block(block_type_id)
        except KeyError:
            yield _log(
                "error", node_id,
                f"Block type '{block_type_id}' is not registered.",
                status="error",
            )
            return

        inputs = self._collect_inputs(node_id)

        # --- Check / install declared pip dependencies ---
        dep_failed = False
        async for msg in _ensure_dependencies(block, node_id):
            yield msg
            if msg.get("status") == "error":
                dep_failed = True
        if dep_failed:
            return

        # --- Composite block: run subflow as nested executor ---
        if isinstance(block, CompositeBlockDefinition):
            async for msg in self._execute_composite(
                node_id, block, inputs, parameters, use_cache
            ):
                yield msg
            # Outputs are stored by _execute_composite; cache at composite level
            save_cache(cache_key, self._outputs.get(node_id, {}))
            yield _log("info", node_id, "Done.", status="done")
            return

        disp_q: queue.SimpleQueue = queue.SimpleQueue()
        token = _disp_queue.set(disp_q)
        exc_caught: Exception | None = None
        try:
            loop = asyncio.get_running_loop()
            # Copy context explicitly so _disp_queue ContextVar is visible in the thread (Python < 3.9 compat).
            ctx = contextvars.copy_context()
            outputs = await loop.run_in_executor(None, ctx.run, block.run, inputs, parameters)
        except Exception as exc:  # noqa: BLE001
            exc_caught = exc
        finally:
            _disp_queue.reset(token)

        while not disp_q.empty():
            yield _log("info", node_id, disp_q.get_nowait(), status="disp")

        if exc_caught is not None:
            yield _log("error", node_id, str(exc_caught), status="error")
            return

        self._outputs[node_id] = outputs
        save_cache(cache_key, outputs)
        yield _log("info", node_id, "Done.", status="done")
        # If the block produced a visualization, broadcast the image
        viz = outputs.get("_viz", {})
        if viz.get("image_b64"):
            yield _log("info", node_id, "Visualization ready.",
                       status="viz_result", image_b64=viz["image_b64"])

    def _collect_inputs(self, node_id: str) -> dict:
        """Gather input port values for a node from upstream node outputs.

        For nodes in a composite subflow, injected_inputs (keyed by node_id)
        may provide values that come from the host workflow instead of an edge.

        Args:
            node_id: Target node whose inputs to collect.

        Returns:
            Dict mapping target port_id -> value from the upstream output port.
        """
        inputs: dict = {}
        # Start with any values injected from the host workflow (composite subflow case)
        if node_id in self._injected_inputs:
            inputs.update(self._injected_inputs[node_id])
        for edge in self.edges:
            if edge["target_node_id"] != node_id:
                continue
            src_outputs = self._outputs.get(edge["source_node_id"], {})
            inputs[edge["target_port_id"]] = src_outputs.get(edge["source_port_id"])
        return inputs

    async def _execute_composite(
        self,
        node_id: str,
        block: "CompositeBlockDefinition",
        inputs: dict,
        parameters: dict,
        use_cache: bool,
    ) -> AsyncGenerator[dict, None]:
        """Run a composite block by executing its embedded subflow as a nested pipeline.

        Args:
            node_id:    Host-workflow node id (used for log prefixing and cache namespacing).
            block:      The CompositeBlockDefinition with subflow + port mappings.
            inputs:     Already-collected input values keyed by the composite's external port_id.
            parameters: (Unused in v1 — composite blocks expose no parameters.)
            use_cache:  Passed through to the nested PipelineExecutor.

        Yields:
            Log message dicts (node_id prefixed with composite name for console).
        """
        # 1. Map composite external inputs -> internal node data-ports or parameters
        injected: dict[str, dict] = {}        # node_id -> {port_id -> value}
        injected_params: dict[str, dict] = {} # node_id -> {param_name -> value}
        for port_def in block.inputs:
            external_id  = port_def["port_id"]
            value        = inputs.get(external_id)
            # Use default only when caller provided no value (unconnected promoted param)
            if value is None:
                value = port_def.get("default")
            if value is None:
                continue

            promoted_from = port_def.get("promoted_from")
            maps_to       = port_def.get("maps_to")

            if promoted_from:
                # Promoted parameter: inject as a parameter override into the target node
                target_node  = promoted_from.get("node_id")
                param_name   = promoted_from.get("parameter")
                if target_node and param_name:
                    injected_params.setdefault(target_node, {})[param_name] = value
            elif maps_to:
                # Data port mapping: inject as an input port value
                target_node = maps_to.get("node_id")
                target_port = maps_to.get("port_id")
                if target_node and target_port:
                    injected.setdefault(target_node, {})[target_port] = value

        # 2. Build subflow dict, adding composite_blocks from the host workflow so nested
        #    composites can resolve their own types.
        subflow = dict(block.subflow)
        # Propagate host composite_blocks into subflow so nested composites work
        host_composite_blocks = self.workflow.get("composite_blocks", [])
        if host_composite_blocks:
            subflow = {**subflow, "composite_blocks": host_composite_blocks}

        # Pre-register any composite blocks embedded in the subflow so that
        # validate_workflow (called by the nested executor) can look them up.
        from core.block_registry import register_block as _reg_block
        from core.library_registry import _block_registry as _registry
        for cb_def in subflow.get("composite_blocks", []):
            if cb_def.get("block_type_id") not in _registry:
                try:
                    _reg_block(CompositeBlockDefinition(cb_def))  # type: ignore[arg-type]
                except Exception:  # noqa: BLE001
                    pass

        # 3. Run subflow via a nested PipelineExecutor
        sub_executor = PipelineExecutor(
            workflow=subflow,
            injected_inputs=injected,
            injected_params=injected_params,
            parent_run_id=node_id,
        )
        async for msg in sub_executor.run(use_cache=use_cache):
            nid = msg.get("node_id")
            if nid:
                # Prefix node_id so console shows e.g.
                # "[phaseprecession / bandpass_003] Done."
                msg = dict(msg)
                msg["node_id"] = f"{node_id}/{nid}"
                yield msg
            elif msg.get("level") == "error":
                # Surface subflow-level validation/import errors (no node_id).
                yield msg
            # else: suppress subflow control messages (plan, pipeline complete,
            # batch progress, stopped) — they would confuse the outer pipeline's
            # status tracking and make the frontend think the whole run is done.

        # 4. Map subflow output ports back to composite's external output ports
        outputs: dict = {}
        for port_def in block.outputs:
            external_id = port_def["port_id"]
            maps_to     = port_def.get("maps_to", {})
            src_node    = maps_to.get("node_id")
            src_port    = maps_to.get("port_id")
            if src_node and src_port:
                src_node_outputs = sub_executor._outputs.get(src_node, {})
                outputs[external_id] = src_node_outputs.get(src_port)

        # Store outputs on self so the host workflow can collect them normally
        self._outputs[node_id] = outputs

    def _get_input_cache_keys(self, node_id: str) -> list[str]:
        """Return the cache keys of all direct predecessor nodes.

        Args:
            node_id: The node whose predecessors to query.

        Returns:
            List of cache key strings for all predecessor nodes that have
            already been processed (may be empty for source nodes).
        """
        keys: list[str] = []
        for edge in self.edges:
            if edge["target_node_id"] == node_id:
                pred_id = edge["source_node_id"]
                if pred_id in self._cache_keys:
                    keys.append(self._cache_keys[pred_id])
        return keys
