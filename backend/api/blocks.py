
from __future__ import annotations

import inspect
import json
import re
import time
import traceback as tb_module
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from blocks.base import BlockBase, CompositeBlockDefinition
from core.validator import validate_connection
from neurodata.port_types import Compat
from core.block_registry import all_blocks, get_block, register_block, unregister_block
from core.library_registry import list_libraries, detect_conflicts

router = APIRouter()

# Directory where user-created block files live
USER_DIR = Path(__file__).resolve().parent.parent / "blocks" / "user"
# Directory where composite block JSON definitions live
COMPOSITE_DIR = Path(__file__).resolve().parent.parent / "blocks" / "composite"

_SAFE_ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')


def _validate_id(block_type_id: str) -> None:
    """Raise HTTPException if block_type_id is not safe to use as a filename."""
    if not block_type_id or not _SAFE_ID_RE.match(block_type_id):
        raise HTTPException(status_code=422, detail={
            "error": "invalid_id",
            "message": (
                f"'{block_type_id}' is not a valid block_type_id. "
                "Only alphanumeric characters, underscores, and hyphens are allowed."
            ),
            "details": {},
        })


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ConnectionRequest(BaseModel):
    output_type: str
    input_type: str


class CustomBlockRequest(BaseModel):
    """Legacy endpoint — registers a block from raw full-class source code."""
    source_code: str
    block_type_id: str = ""
    display_name: str = ""
    category: str = ""
    description: str = ""
    inputs: list[dict] = []
    outputs: list[dict] = []
    parameters: list[dict] = []


class CreateBlockRequest(BaseModel):
    """Wizard-based block creation: structured metadata + user snippet."""
    block_type_id: str
    display_name: str
    category: str
    description: str = ""
    inputs: list[dict] = []
    outputs: list[dict] = []
    parameters: list[dict] = []
    source_snippet: str = ""
    dependencies: list[str] = []


class TestRunRequest(BaseModel):
    source_snippet: str
    inputs: list[dict] = []
    outputs: list[dict] = []
    parameters: list[dict] = []


class RegisterLocalBlocksRequest(BaseModel):
    """Register local block definitions from a workflow (in-memory only, no disk write)."""
    local_blocks: list[dict] = []


class PackageBlockRequest(BaseModel):
    """Package the current workflow as a composite block."""
    workflow: dict
    metadata: dict                       # block_type_id, display_name, category, description
    input_mappings: list[dict] = []      # [{external_port_id, node_id, port_id, data_type}]
    output_mappings: list[dict] = []     # [{external_port_id, node_id, port_id, data_type}]
    promoted_parameters: list[dict] = [] # [{external_port_id, node_id, parameter, default}]
    library_id: str = "user_blocks"      # target library for the composite JSON file


class SaveLocalToLibraryRequest(BaseModel):
    """Promote a workflow-local block to a permanent library block on disk."""
    block_def: dict    # CreateBlockRequest-compatible local block definition
    library_id: str    # target library ID (must be non-builtin)


# ---------------------------------------------------------------------------
# Code-generation helpers
# ---------------------------------------------------------------------------

def _pascal_case(s: str) -> str:
    return "".join(w.capitalize() for w in re.split(r"[_\-\s]+", s) if w)


def _esc(s: str) -> str:
    """Escape a string for safe embedding inside a double-quoted Python literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", "\\n")


def _ensure_user_dir() -> None:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    init = USER_DIR / "__init__.py"
    if not init.exists():
        init.write_text("# SynapChart user-defined blocks.\n", encoding="utf-8")


def _generate_block_code(req: CreateBlockRequest) -> str:
    # Use only the short (un-namespaced) part for the Python class name so that
    # a block_type_id like "synapchart_builtin.load_crcns_lfp_variant" doesn't
    # produce an invalid class name containing a dot.
    short_id   = req.block_type_id.split(".")[-1] if "." in req.block_type_id else req.block_type_id
    class_name = _pascal_case(short_id)

    def _fmt_port(p: dict, with_required: bool) -> str:
        desc = _esc(p.get("description", ""))
        line = (
            f'        PortDefinition(port_id="{p["port_id"]}", '
            f'data_type="{p["data_type"]}", description="{desc}"'
        )
        if with_required:
            req_val = "True" if p.get("required", True) else "False"
            line += f", required={req_val}"
        return line + "),"

    def _fmt_param(p: dict) -> str:
        dtype = p["data_type"]
        if dtype == "enum":
            dtype = f"enum:{p.get('enum_values', '')}"
        raw = p["data_type"]
        default = p.get("default", "")
        if raw in ("str", "enum"):
            default_repr = f'"{_esc(str(default))}"'
        elif raw == "bool":
            default_repr = "True" if str(default).lower() in ("true", "1", "yes") else "False"
        elif raw == "float":
            try:
                default_repr = str(float(default))
            except (ValueError, TypeError):
                default_repr = "0.0"
        elif raw == "int":
            try:
                default_repr = str(int(float(default)))
            except (ValueError, TypeError):
                default_repr = "0"
        else:
            default_repr = f'"{_esc(str(default))}"'
        desc = _esc(p.get("description", ""))
        return (
            f'        ParameterDefinition(name="{p["name"]}", data_type="{dtype}", '
            f"default={default_repr}, description=\"{desc}\"),"
        )

    inputs_lines  = [_fmt_port(p, with_required=True)  for p in req.inputs]
    outputs_lines = [_fmt_port(p, with_required=False) for p in req.outputs]
    params_lines  = [_fmt_param(p) for p in req.parameters]

    # Indent snippet: 8 spaces inside run()
    snippet_lines = [
        ("        " + line) if line.strip() else ""
        for line in req.source_snippet.splitlines()
    ]

    desc = _esc(req.description)

    deps_repr = repr(req.dependencies)

    parts = [
        f"# backend/blocks/user/{req.block_type_id}.py",
        "# Auto-generated by SynapChart custom block editor.",
        "# You can edit this file directly — changes take effect on server restart.",
        "",
        "from blocks.base import BlockBase, PortDefinition, ParameterDefinition",
        "from neurodata.types import NeuroData",
        "import numpy as np",
        "",
        "",
        f"class {class_name}(BlockBase):",
        "",
        f'    block_type_id = "{req.block_type_id}"',
        f'    display_name  = "{_esc(req.display_name)}"',
        f'    category      = "{_esc(req.category)}"',
        f'    description   = "{desc}"',
        "    is_custom     = True",
        f"    _dependencies = {deps_repr}",
        "",
        "    inputs = [",
        *inputs_lines,
        "    ]",
        "    outputs = [",
        *outputs_lines,
        "    ]",
        "    parameters = [",
        *params_lines,
        "    ]",
        "",
        "    def run(self, inputs, parameters):",
        "        # --- User code start ---",
        "        # numpy, NeuroData, Path and disp() are always available; import anything else you need:",
        "        import numpy as np",
        "        from pathlib import Path",
        "        from neurodata.types import NeuroData",
        *snippet_lines,
        "        # --- User code end ---",
        "",
    ]
    return "\n".join(parts)


def _exec_and_register(code: str, source_path: str) -> BlockBase:
    """Exec generated class code and register it. Returns the instance."""
    namespace: dict[str, Any] = {}
    exec(compile(code, source_path, "exec"), namespace)  # noqa: S102
    cls = next(
        (v for v in namespace.values()
         if isinstance(v, type) and issubclass(v, BlockBase) and v is not BlockBase),
        None,
    )
    if cls is None:
        raise ValueError("Generated code contains no BlockBase subclass.")
    instance = cls()
    instance._source_code = code  # stored for retrieval when inspect.getsource fails on exec'd classes
    register_block(instance)
    return instance


def _register_local_block_definitions(local_blocks: list[dict]) -> tuple[list, list]:
    """Register a list of local block definitions in-memory (no disk write).

    Used both by the /register-local endpoint and by files.py when loading
    a workflow that contains a local_blocks array.

    Returns:
        (registered, errors) where each is a list.
    """
    registered: list[str] = []
    errors: list[dict] = []
    for block_def in local_blocks:
        try:
            req = CreateBlockRequest(**block_def)
            code = _generate_block_code(req)
            instance = _exec_and_register(code, f"<local:{req.block_type_id}>")
            registered.append(instance.block_type_id)
        except Exception as exc:  # noqa: BLE001
            errors.append({
                "block_type_id": block_def.get("block_type_id", "?"),
                "error": str(exc),
            })
    return registered, errors


# ---------------------------------------------------------------------------
# Test-run helpers
# ---------------------------------------------------------------------------

def _make_dummy_inputs(inputs_spec: list[dict]) -> dict:
    import numpy as np
    from neurodata.types import NeuroData

    rng = np.random.default_rng(42)
    dummy: dict = {}
    for inp in inputs_spec:
        dtype = inp.get("data_type", "")
        pid   = inp["port_id"]
        # All continuous NeuroData types are generated as 2-D (samples × channels)
        # with channel_names so that blocks can safely use arr[:, idx] or check ndim.
        # Using 4 channels covers common multi-channel use-cases; blocks that only
        # need 1-D can still do arr[:, 0] or squeeze as needed.
        if dtype in ("NeuroData[raw_signal]", "NeuroData[lfp]"):
            t = np.linspace(0, 1, 1000)
            arr = np.column_stack([
                np.sin(2 * np.pi * (8 + i * 2) * t) for i in range(4)
            ])  # shape (1000, 4)
            dummy[pid] = NeuroData(
                data_type=dtype[10:-1], array=arr, sampling_rate=1000.0,
                channel_names=[f"ch{i}" for i in range(4)],
                timestamps=t,
            )
        elif dtype == "NeuroData[spike_times]":
            dummy[pid] = NeuroData(data_type="spike_times",
                                   array=np.sort(rng.uniform(0, 10, 50)), sampling_rate=1.0)
        elif dtype == "NeuroData[spike_matrix]":
            dummy[pid] = NeuroData(data_type="spike_matrix",
                                   array=rng.integers(0, 2, (10, 100)).astype(float),
                                   sampling_rate=1000.0)
        elif dtype == "NeuroData[position]":
            t = np.linspace(0, 10, 300)
            dummy[pid] = NeuroData(data_type="position",
                                   array=np.column_stack([t, np.linspace(0, 100, 300), np.zeros(300)]),
                                   sampling_rate=30.0)
        elif dtype in ("NeuroData[tuning_curve]", "NeuroData[decoded]", "NeuroData[any]"):
            dummy[pid] = NeuroData(data_type=dtype[10:-1],
                                   array=rng.random(100), sampling_rate=1.0)
        elif dtype == "float":
            dummy[pid] = 1.0
        elif dtype == "int":
            dummy[pid] = 1
        elif dtype == "bool":
            dummy[pid] = True
        else:
            dummy[pid] = "test"
    return dummy


def _make_dummy_params(params_spec: list[dict]) -> dict:
    dummy: dict = {}
    for p in params_spec:
        raw = p.get("data_type", "str")
        default = p.get("default", "")
        if raw == "float":
            try:    dummy[p["name"]] = float(default)
            except (ValueError, TypeError): dummy[p["name"]] = 0.0
        elif raw == "int":
            try:    dummy[p["name"]] = int(float(default))
            except (ValueError, TypeError): dummy[p["name"]] = 0
        elif raw == "bool":
            dummy[p["name"]] = str(default).lower() in ("true", "1", "yes")
        else:
            dummy[p["name"]] = str(default)
    return dummy


# ---------------------------------------------------------------------------
# Endpoints — read-only
# ---------------------------------------------------------------------------

@router.get("/")
async def list_blocks(libraries: str = "") -> dict:
    """List registered blocks grouped by library then by category.

    Optional ``?libraries=id1,id2`` query param filters to only those library IDs.
    The response includes both the new ``libraries`` array (for the library-aware
    side panel) and a flat ``categories`` array (backward compatibility).
    """
    filter_ids: set[str] | None = None
    if libraries:
        filter_ids = {lid.strip() for lid in libraries.split(",") if lid.strip()}

    manifests = list_libraries()

    library_groups: list[dict] = []
    flat_by_cat: dict[str, list[dict]] = {}

    for manifest in manifests:
        if filter_ids is not None and manifest.id not in filter_ids:
            continue
        prefix = f"{manifest.id}."
        by_cat: dict[str, list[dict]] = {}
        for block_id, block in all_blocks().items():
            if not block_id.startswith(prefix):
                continue
            defn = block.to_definition()
            defn["block_type_id"] = block_id   # ensure namespaced ID
            raw_cat = defn.get("category") or "Uncategorized"
            # Strip redundant library-id prefix so categories are clean inside
            # their library section, mirroring the folder structure.
            # e.g. "maze1d / Analysis" inside library "maze1d" → "Analysis"
            for sep in (f"{manifest.id} / ", f"{manifest.id}/"):
                if raw_cat.startswith(sep):
                    raw_cat = raw_cat[len(sep):]
                    break
            cat = raw_cat
            by_cat.setdefault(cat, []).append(defn)
            flat_by_cat.setdefault(cat, []).append(defn)
        if by_cat:
            library_groups.append({
                "id":         manifest.id,
                "name":       manifest.name,
                "group":      manifest.group,
                "version":    manifest.version,
                "is_builtin": manifest.is_builtin,
                "categories": [
                    {"name": cat, "blocks": blks}
                    for cat, blks in sorted(by_cat.items())
                ],
            })

    flat_categories = [
        {"name": cat, "blocks": blks}
        for cat, blks in sorted(flat_by_cat.items())
    ]
    return {"libraries": library_groups, "categories": flat_categories}


@router.get("/{block_type_id}/source")
async def get_block_source(block_type_id: str) -> dict:
    """Return the source code of a registered block.

    For custom blocks, also returns the extracted user snippet
    (the code between the --- User code start/end --- markers).
    """
    try:
        block = get_block(block_type_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={
            "error": "block_not_found",
            "message": f"Block type '{block_type_id}' is not registered.",
            "details": {},
        })
    try:
        source = inspect.getsource(type(block))
    except (OSError, TypeError):
        # exec'd classes (local blocks) have no backing file; fall back to stored code
        source = getattr(block, '_source_code', None)

    is_custom = getattr(type(block), "is_custom", False)
    source_snippet: str | None = None

    dependencies: list[str] = list(getattr(type(block), "_dependencies", []) or [])

    if is_custom and source:
        lines = source.splitlines()
        start = next((i for i, l in enumerate(lines) if "# --- User code start ---" in l), None)
        end   = next((i for i, l in enumerate(lines) if "# --- User code end ---"   in l), None)
        if start is not None and end is not None:
            # Skip the four auto-injected lines after the start marker:
            #   [comment] [import numpy as np] [from pathlib import Path] [from neurodata.types import NeuroData]
            raw_lines = lines[start + 5 : end]
            source_snippet = "\n".join(
                l[8:] if l.startswith("        ") else l
                for l in raw_lines
            )
    elif not is_custom:
        # For built-in blocks: extract the run() method body so duplicating gives
        # a useful starting point rather than an empty editor.
        # Also extract any helper methods (e.g. @staticmethod _read_xml) and inline
        # them as top-level functions so the generated local variant is self-contained.
        import textwrap
        try:
            cls = type(block)

            # Collect helper functions defined directly on this class.
            # We include any name that is a function/staticmethod/classmethod,
            # is not a dunder, and is not 'run'.
            helper_snippets: list[str] = []
            helper_names: list[str] = []

            for attr_name, attr_val in cls.__dict__.items():
                if attr_name.startswith("__") or attr_name == "run":
                    continue
                # Unwrap staticmethod / classmethod to get the underlying function
                if isinstance(attr_val, staticmethod):
                    fn = attr_val.__func__
                elif isinstance(attr_val, classmethod):
                    fn = attr_val.__func__
                elif callable(attr_val):
                    fn = attr_val
                else:
                    continue  # class attribute, not a method

                try:
                    helper_src = inspect.getsource(fn)
                    lines = helper_src.splitlines()
                    # Strip decorator lines (@staticmethod, @classmethod) that were
                    # on the function in the original class — they're invalid on a
                    # top-level function and are handled implicitly.
                    lines = [
                        l for l in lines
                        if l.strip() not in ("@staticmethod", "@classmethod")
                    ]
                    dedented = textwrap.dedent("\n".join(lines)).strip()
                    helper_snippets.append(dedented)
                    helper_names.append(attr_name)
                except (OSError, TypeError):
                    pass

            run_src = inspect.getsource(cls.run)
            run_lines = run_src.splitlines()
            # Find the first line after "def run(..."
            body_start = next(
                (i + 1 for i, l in enumerate(run_lines) if l.lstrip().startswith("def run")),
                None,
            )
            if body_start is not None:
                run_body = textwrap.dedent("\n".join(run_lines[body_start:])).strip()
                # Replace self._helper( with _helper( so standalone functions are called
                for hname in helper_names:
                    run_body = run_body.replace(f"self.{hname}(", f"{hname}(")

                if helper_snippets:
                    source_snippet = "\n\n".join(helper_snippets) + "\n\n" + run_body
                else:
                    source_snippet = run_body
        except (OSError, TypeError):
            pass

    return {
        "source_code": source,
        "source_snippet": source_snippet,
        "is_custom": is_custom,
        "dependencies": dependencies,
    }


@router.get("/{block_type_id}")
async def get_block_definition(block_type_id: str) -> dict:
    """Get full definition of one block type."""
    try:
        return get_block(block_type_id).to_definition()
    except KeyError:
        raise HTTPException(status_code=404, detail={
            "error": "block_not_found",
            "message": f"Block type '{block_type_id}' is not registered.",
            "details": {},
        })


@router.post("/validate-connection")
async def validate_connection_endpoint(request: ConnectionRequest) -> dict:
    status, message = validate_connection(request.output_type, request.input_type)
    # `valid` stays back-compatible (WARN is connectable); `status` is the new
    # three-state value ("ok"|"warn"|"error") the canvas UI consumes.
    return {"valid": status is not Compat.ERROR, "status": status.value, "message": message}


# ---------------------------------------------------------------------------
# Endpoints — custom block CRUD
# ---------------------------------------------------------------------------

@router.post("/test-run")
async def test_run_block(request: TestRunRequest) -> dict:
    """Execute a user snippet with dummy data and return output types or errors."""
    import numpy as np
    from neurodata.types import NeuroData

    dummy_inputs = _make_dummy_inputs(request.inputs)
    dummy_params = _make_dummy_params(request.parameters)

    # Wrap snippet in a function so `return` is valid
    wrapped = "def _user_run(inputs, parameters):\n"
    for line in request.source_snippet.splitlines():
        wrapped += "    " + line + "\n"
    if not request.source_snippet.strip():
        wrapped += "    return {}\n"

    global_ns: dict[str, Any] = {
        "__builtins__": __builtins__,
        "np": np,
        "numpy": np,
        "NeuroData": NeuroData,
    }

    try:
        exec(compile(wrapped, "<test-run>", "exec"), global_ns)  # noqa: S102
    except SyntaxError as exc:
        return {
            "status": "error",
            "error_type": "syntax_error",
            "message": str(exc),
            "traceback": str(exc),
            "line_number": (exc.lineno - 1) if exc.lineno else None,
        }

    t0 = time.perf_counter()
    try:
        result = global_ns["_user_run"](dummy_inputs, dummy_params)
    except Exception as exc:  # noqa: BLE001
        tb_str = tb_module.format_exc()
        match = re.search(r'File "<test-run>", line (\d+)', tb_str)
        line_num = (int(match.group(1)) - 1) if match else None
        return {
            "status": "warning",
            "error_type": "runtime_exception",
            "message": (
                f"{type(exc).__name__}: {exc}\n\n"
                "Note: the test runner uses synthetic dummy data — this error may be caused "
                "by a shape or value mismatch between the dummy input and what your code "
                "expects. Your block will still be saved; verify with real data at runtime."
            ),
            "traceback": tb_str,
            "line_number": line_num,
        }
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if result is None:
        result = {}

    output_types: dict[str, str] = {}
    warnings: list[str] = []
    for out in request.outputs:
        pid      = out["port_id"]
        expected = out.get("data_type", "")
        if pid not in result:
            warnings.append(f"Output '{pid}' was not returned.")
            output_types[pid] = "missing"
            continue
        val = result[pid]
        actual = f"NeuroData[{val.data_type}]" if hasattr(val, "data_type") else type(val).__name__
        output_types[pid] = actual
        if actual != expected and expected not in ("NeuroData[any]", ""):
            warnings.append(f"Output '{pid}': expected {expected}, got {actual}.")

    return {
        "status": "ok",
        "output_types": output_types,
        "execution_time_ms": round(elapsed_ms, 1),
        "warnings": warnings,
    }


@router.post("/create")
async def create_block(request: CreateBlockRequest) -> dict:
    """Generate, save to disk, and register a new custom block."""
    _validate_id(request.block_type_id)
    _ensure_user_dir()
    code   = _generate_block_code(request)
    target = USER_DIR / f"{request.block_type_id}.py"
    target.write_text(code, encoding="utf-8")
    try:
        instance = _exec_and_register(code, str(target))
    except Exception as exc:  # noqa: BLE001
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail={
            "error": "code_generation_failed",
            "message": str(exc),
            "details": {},
        })
    return {"status": "created", "block_type_id": instance.block_type_id,
            "definition": instance.to_definition()}


@router.put("/{block_type_id}")
async def update_block(block_type_id: str, request: CreateBlockRequest) -> dict:
    """Overwrite an existing block's file and re-register it.

    Works for both custom (user) blocks and built-in blocks.
    For built-in blocks the change is written directly to the built-in
    source file so the edit persists across server restarts.
    """
    try:
        existing = get_block(block_type_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={
            "error": "block_not_found",
            "message": f"Block '{block_type_id}' is not registered.",
            "details": {},
        })

    code = _generate_block_code(request)
    is_custom = getattr(type(existing), "is_custom", False)

    if is_custom:
        _ensure_user_dir()
        target = USER_DIR / f"{block_type_id}.py"
    else:
        # Built-in block — write to the original source file so the change persists
        try:
            source_file = Path(inspect.getfile(type(existing)))
            target = source_file
        except (TypeError, OSError):
            # exec'd or otherwise unlocatable → fall back to user dir
            _ensure_user_dir()
            target = USER_DIR / f"{block_type_id}.py"

    target.write_text(code, encoding="utf-8")
    try:
        instance = _exec_and_register(code, str(target))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail={
            "error": "code_generation_failed",
            "message": str(exc),
            "details": {},
        })
    return {"status": "updated", "block_type_id": instance.block_type_id,
            "definition": instance.to_definition()}


@router.patch("/{block_type_id}/category")
async def update_block_category(block_type_id: str, body: dict) -> dict:
    """Move a custom block to a different category (rewrites the .py file in-place)."""
    new_category = (body.get("category") or "").strip()
    if not new_category:
        raise HTTPException(status_code=422, detail={
            "error": "invalid_category",
            "message": "Category name cannot be empty.",
            "details": {},
        })
    try:
        block = get_block(block_type_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={
            "error": "block_not_found",
            "message": f"Block '{block_type_id}' is not registered.",
            "details": {},
        })
    if not getattr(type(block), "is_custom", False):
        raise HTTPException(status_code=403, detail={
            "error": "not_custom",
            "message": f"'{block_type_id}' is a built-in block; its category cannot be changed.",
            "details": {},
        })
    target = USER_DIR / f"{block_type_id}.py"
    if not target.exists():
        raise HTTPException(status_code=404, detail={
            "error": "file_not_found",
            "message": f"Block file for '{block_type_id}' not found on disk.",
            "details": {},
        })
    code = target.read_text(encoding="utf-8")
    escaped = _esc(new_category)
    code = re.sub(
        r'(    category\s*=\s*)"[^"]*"',
        lambda _m: f'    category      = "{escaped}"',
        code,
    )
    target.write_text(code, encoding="utf-8")
    _exec_and_register(code, str(target))
    return {"status": "ok", "block_type_id": block_type_id, "category": new_category}


@router.delete("/{block_type_id}")
async def delete_block(block_type_id: str) -> dict:
    """Delete a custom block from disk and the registry."""
    try:
        block = get_block(block_type_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={
            "error": "block_not_found",
            "message": f"Block '{block_type_id}' is not registered.",
            "details": {},
        })
    if not getattr(type(block), "is_custom", False):
        raise HTTPException(status_code=403, detail={
            "error": "not_custom",
            "message": f"'{block_type_id}' is a built-in block and cannot be deleted.",
            "details": {},
        })
    target = USER_DIR / f"{block_type_id}.py"
    target.unlink(missing_ok=True)
    unregister_block(block_type_id)
    return {"status": "deleted", "block_type_id": block_type_id}


@router.post("/register-local")
async def register_local_blocks(request: RegisterLocalBlocksRequest) -> dict:
    """Temporarily register local block definitions from a workflow.

    Called when a new local block is created via the wizard, or when a workflow
    is loaded programmatically (e.g. via the frontend after a /api/files/load call).
    Blocks are registered in-memory only — nothing is written to disk.
    """
    registered, errors = _register_local_block_definitions(request.local_blocks)
    return {"status": "ok", "registered": registered, "errors": errors}


@router.post("/register-custom")
async def register_custom(request: CustomBlockRequest) -> dict:
    """Register a block from a full class source string.

    The source is typically the output of ``inspect.getsource(cls)`` — just the
    class body, without file-level imports.  We pre-populate the exec namespace
    with the standard imports so the class definition compiles correctly even
    when those imports are absent from the source string.
    """
    import numpy as _np
    from blocks.base import (  # noqa: PLC0415
        BlockBase as _BlockBase,
        ParameterDefinition as _PD,
        PortDefinition as _Port,
    )
    from neurodata.types import NeuroData as _ND  # noqa: PLC0415

    namespace: dict = {
        "__builtins__": __builtins__,
        # Standard names available inside every library block
        "BlockBase":           _BlockBase,
        "ParameterDefinition": _PD,
        "PortDefinition":      _Port,
        "NeuroData":           _ND,
        "np":                  _np,
        "numpy":               _np,
        "Any":                 Any,
    }

    try:
        exec(  # noqa: S102
            compile(request.source_code,
                    f"<custom:{request.block_type_id or 'unknown'}>",
                    "exec"),
            namespace,
        )
    except SyntaxError as exc:
        raise HTTPException(status_code=422, detail={
            "error": "syntax_error",
            "message": f"SyntaxError on line {exc.lineno}: {exc.msg}",
            "details": {"lineno": exc.lineno, "text": exc.text},
        }) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail={
            "error": "invalid_block_source",
            "message": f"{type(exc).__name__}: {exc}",
            "details": {},
        }) from exc

    cls = next(
        (v for v in namespace.values()
         if isinstance(v, type) and issubclass(v, _BlockBase) and v is not _BlockBase),
        None,
    )
    if cls is None:
        raise HTTPException(status_code=422, detail={
            "error": "invalid_block_source",
            "message": "Source code must define exactly one BlockBase subclass.",
            "details": {},
        })
    instance = cls()
    # Store source so get_block_source can return it (exec'd classes have no backing file).
    instance._source_code = request.source_code  # type: ignore[attr-defined]
    register_block(instance)
    return {"status": "registered", "block_type_id": instance.block_type_id}


# ---------------------------------------------------------------------------
# Library-aware directory helpers
# ---------------------------------------------------------------------------

from core.library_registry import (  # noqa: E402 — after module-level imports
    USER_BLOCKS_LIBRARY_ID as _USER_BLOCKS_LIB_ID,
    LEGACY_COMPOSITE_DIR   as _LEGACY_COMPOSITE_DIR,
)


def _library_blocks_dir(manifest) -> Path:
    """Return the directory where .py block files for ``manifest`` should be written.

    ``user_blocks`` stores files directly in ``backend/blocks/user/``.
    All other libraries store files in ``<library_root>/blocks/``.
    """
    if manifest.id == _USER_BLOCKS_LIB_ID:
        return USER_DIR                   # backend/blocks/user/
    return manifest.path / "blocks"


def _library_composite_dir(manifest) -> Path:
    """Return the directory where composite JSON files for ``manifest`` go.

    ``user_blocks`` stores files in ``backend/blocks/composite/``.
    All other libraries store files in ``<library_root>/composite/``.
    """
    if manifest.id == _USER_BLOCKS_LIB_ID:
        return _LEGACY_COMPOSITE_DIR      # backend/blocks/composite/
    return manifest.path / "composite"


# ---------------------------------------------------------------------------
# Save local block to library
# ---------------------------------------------------------------------------

@router.post("/save-local-to-library")
async def save_local_to_library(request: SaveLocalToLibraryRequest) -> dict:
    """Promote a workflow-local block to a permanent file on disk in a chosen library.

    The block's Python file is written to the target library's ``blocks/``
    directory and the block is immediately registered in the global registry
    under ``<library_id>.<block_type_id>``.  The workflow's ``local_blocks``
    entry is left untouched — it continues to make the workflow self-contained.
    """
    from core.library_registry import _libraries, register_block as _lib_register

    lib = _libraries.get(request.library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail={
            "error": "library_not_found",
            "message": f"Library '{request.library_id}' is not loaded.",
            "details": {},
        })
    if lib.is_builtin:
        raise HTTPException(status_code=403, detail={
            "error": "readonly_library",
            "message": f"Library '{request.library_id}' is read-only (built-in or bundled).",
            "details": {},
        })

    try:
        req = CreateBlockRequest(**request.block_def)
    except Exception as exc:
        raise HTTPException(status_code=422, detail={
            "error": "invalid_block_def",
            "message": str(exc),
            "details": {},
        })

    # Validate short ID (no dots — the library prefix is added by the registry)
    short_id = req.block_type_id.split(".")[-1] if "." in req.block_type_id else req.block_type_id
    _validate_id(short_id)

    # Use the short ID in the generated code so the file is portable
    req_short = CreateBlockRequest(
        block_type_id = short_id,
        display_name  = req.display_name,
        category      = req.category,
        description   = req.description,
        inputs        = req.inputs,
        outputs       = req.outputs,
        parameters    = req.parameters,
        source_snippet = req.source_snippet,
        dependencies  = req.dependencies,
    )

    target_dir = _library_blocks_dir(lib)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Create __init__.py for user_blocks (package import compatibility)
    if lib.id == _USER_BLOCKS_LIB_ID:
        _ensure_user_dir()

    code        = _generate_block_code(req_short)
    target_file = target_dir / f"{short_id}.py"
    target_file.write_text(code, encoding="utf-8")

    # Exec the code and register under the correct library namespace
    try:
        namespace: dict = {}
        exec(compile(code, str(target_file), "exec"), namespace)  # noqa: S102
        cls = next(
            (v for v in namespace.values()
             if isinstance(v, type) and issubclass(v, BlockBase) and v is not BlockBase),
            None,
        )
        if cls is None:
            raise ValueError("Generated code contains no BlockBase subclass.")
        instance = cls()
        instance._source_code = code  # type: ignore[attr-defined]
        _lib_register(instance, request.library_id)
    except Exception as exc:
        target_file.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail={
            "error": "registration_failed",
            "message": str(exc),
            "details": {},
        })

    namespaced_id = f"{request.library_id}.{short_id}"
    return {
        "status":         "saved",
        "block_type_id":  namespaced_id,
        "library_id":     request.library_id,
        "file_path":      str(target_file),
        "definition":     instance.to_definition(),
    }


# ---------------------------------------------------------------------------
# Composite block endpoints
# ---------------------------------------------------------------------------

def _ensure_composite_dir() -> None:
    COMPOSITE_DIR.mkdir(parents=True, exist_ok=True)


def _composite_file(block_type_id: str) -> Path:
    """Return the .json path for a composite block, stripping any library prefix.

    Composite block files are stored as ``<short_id>.json`` (e.g. ``phaseprecession.json``).
    The namespaced ID the frontend uses (e.g. ``user_blocks.phaseprecession``) must be
    stripped down to just the short ID before constructing the path.
    """
    short_id = block_type_id.split(".", 1)[-1]
    return COMPOSITE_DIR / f"{short_id}.json"


def _register_composite(definition: dict) -> None:
    """Register a CompositeBlockDefinition in the global registry."""
    cbd = CompositeBlockDefinition(definition)
    register_block(cbd)  # type: ignore[arg-type]  — registry accepts any object with block_type_id


@router.post("/package")
async def package_block(request: PackageBlockRequest) -> dict:
    """Package the current workflow as a composite block JSON file."""
    meta = request.metadata
    block_type_id = meta.get("block_type_id", "").strip()
    if not block_type_id:
        raise HTTPException(status_code=422, detail={
            "error": "missing_block_type_id",
            "message": "metadata.block_type_id is required.",
            "details": {},
        })
    _validate_id(block_type_id)

    # Build the inputs / outputs port lists with maps_to / promoted_from linkage
    def _build_data_port(mapping: dict) -> dict:
        return {
            "port_id":     mapping["external_port_id"],
            "data_type":   mapping.get("data_type", "NeuroData[any]"),
            "description": mapping.get("description", ""),
            "maps_to": {
                "node_id": mapping["node_id"],
                "port_id": mapping["port_id"],
            },
        }

    def _build_promoted_port(mapping: dict) -> dict:
        return {
            "port_id":      mapping["external_port_id"],
            "data_type":    "str",
            "description":  mapping.get("description", ""),
            "promoted_from": {
                "node_id":   mapping["node_id"],
                "parameter": mapping["parameter"],
            },
            "default": mapping.get("default", ""),
        }

    # Promoted parameter ports come first so they appear at the top of the input list
    promoted_ports = [_build_promoted_port(m) for m in request.promoted_parameters]
    data_ports     = [_build_data_port(m) for m in request.input_mappings]

    definition: dict = {
        "schema_version": "1.0",
        "block_type":     "composite",
        "block_type_id":  block_type_id,
        "display_name":   meta.get("display_name", block_type_id),
        "category":       meta.get("category", "Composite"),
        "description":    meta.get("description", ""),
        "inputs":  promoted_ports + data_ports,
        "outputs": [_build_data_port(m) for m in request.output_mappings],
        "subflow": {
            "nodes":        request.workflow.get("nodes", []),
            "edges":        request.workflow.get("edges", []),
            "local_blocks": request.workflow.get("local_blocks", []),
        },
    }

    # Resolve target library for the composite JSON file
    from core.library_registry import _libraries
    target_lib_id = request.library_id or _USER_BLOCKS_LIB_ID
    target_lib    = _libraries.get(target_lib_id)

    if target_lib is None or target_lib.is_builtin:
        # Fall back to legacy composite dir if library is unknown or read-only
        target_lib_id = _USER_BLOCKS_LIB_ID
        comp_dir = _LEGACY_COMPOSITE_DIR
    else:
        comp_dir = _library_composite_dir(target_lib)

    comp_dir.mkdir(parents=True, exist_ok=True)
    dest = comp_dir / f"{block_type_id}.json"
    dest.write_text(json.dumps(definition, indent=2), encoding="utf-8")
    _register_composite(definition)

    return {"status": "created", "block_type_id": block_type_id,
            "library_id": target_lib_id,
            "definition": CompositeBlockDefinition(definition).to_definition()}


@router.get("/composite/")
async def list_composite_blocks() -> dict:
    """List all saved composite block definitions."""
    _ensure_composite_dir()
    blocks_list = []
    for f in sorted(COMPOSITE_DIR.glob("*.json")):
        try:
            defn = json.loads(f.read_text(encoding="utf-8"))
            blocks_list.append(CompositeBlockDefinition(defn).to_definition())
        except Exception:  # noqa: BLE001
            pass
    return {"composite_blocks": blocks_list}


@router.get("/composite/{block_type_id}")
async def get_composite_block(block_type_id: str) -> dict:
    """Return the full definition (including subflow) of a composite block."""
    dest = _composite_file(block_type_id)
    if not dest.exists():
        raise HTTPException(status_code=404, detail={
            "error": "composite_not_found",
            "message": f"Composite block '{block_type_id}' not found.",
            "details": {},
        })
    return json.loads(dest.read_text(encoding="utf-8"))


@router.put("/composite/{block_type_id}")
async def update_composite_block(block_type_id: str, definition: dict) -> dict:
    """Overwrite a composite block definition on disk and re-register it."""
    dest = _composite_file(block_type_id)
    if not dest.exists():
        raise HTTPException(status_code=404, detail={
            "error": "composite_not_found",
            "message": f"Composite block '{block_type_id}' not found.",
            "details": {},
        })
    _ensure_composite_dir()
    dest.write_text(json.dumps(definition, indent=2), encoding="utf-8")
    _register_composite(definition)
    return {"status": "updated", "block_type_id": block_type_id}


@router.delete("/composite/{block_type_id}")
async def delete_composite_block(block_type_id: str) -> dict:
    """Delete a composite block from disk and the registry.

    Succeeds even when the backing .json file is absent (e.g. the block was
    registered only in memory during this session, or the file was deleted
    externally).  The block is always unregistered so it disappears from the
    sidebar.  A 404 is returned only if the block is not in the registry at all.
    """
    # Confirm the block is actually known before doing anything
    try:
        get_block(block_type_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={
            "error": "composite_not_found",
            "message": f"Composite block '{block_type_id}' is not registered.",
            "details": {},
        })
    # Remove the file if it exists; missing_ok so memory-only blocks still work
    _composite_file(block_type_id).unlink(missing_ok=True)
    unregister_block(block_type_id)
    return {"status": "deleted", "block_type_id": block_type_id}
