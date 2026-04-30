from __future__ import annotations

import inspect
import json
import logging
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from api.blocks import _register_composite

logger = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r'^[A-Za-z0-9_-]+$')

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "workflows" / "templates"


class SaveRequest(BaseModel):
    workflow: dict
    file_path: str


class LoadRequest(BaseModel):
    file_path: str


class PackRequest(BaseModel):
    workflow: dict
    file_path: str   # output path for the packed .json


class ExtractBlockRequest(BaseModel):
    packed_workflow_path: str
    block_type_id: str    # namespaced ID of block to extract
    target_library_id: str


def _list_windows_drives() -> dict:
    """Return a virtual 'drives' listing for Windows."""
    import string
    drives = []
    for letter in string.ascii_uppercase:
        drive = Path(f"{letter}:\\")
        if drive.exists():
            drives.append({"name": f"{letter}:\\", "path": str(drive), "is_dir": True})
    return {"current_path": "", "parent_path": None, "entries": drives}


@router.get("/browse")
async def browse_files(path: str = "") -> dict:
    """List files and sub-directories at a given path for the file picker."""
    import platform
    is_windows = platform.system() == "Windows"

    if not path:
        if is_windows:
            return _list_windows_drives()
        target = Path.home()
    else:
        target = Path(path)

    if not target.exists():
        raise HTTPException(status_code=404, detail={
            "error": "path_not_found",
            "message": f"Path does not exist: {path}",
            "details": {},
        })

    if target.is_file():
        target = target.parent

    entries = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            try:
                entries.append({
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": entry.is_dir(),
                })
            except PermissionError:
                pass
    except PermissionError:
        pass

    at_drive_root = is_windows and str(target.parent) == str(target)
    parent = "" if at_drive_root else (str(target.parent) if str(target.parent) != str(target) else None)

    return {"current_path": str(target), "parent_path": parent, "entries": entries}


# ---------------------------------------------------------------------------
# Schema migration: v1 → v2
# ---------------------------------------------------------------------------

def _migrate_v1_to_v2(workflow: dict) -> tuple[dict, list[dict]]:
    """Upgrade a schema_version 1.0 workflow to 2.0 (namespaced block IDs).

    Returns:
        (migrated_workflow, forwarding_redirects)
        where forwarding_redirects is a list of {old_id, new_id} dicts for
        blocks that were resolved via forwarding aliases.
    """
    from core.library_registry import _flat_index, _forwarding_aliases

    redirects: list[dict] = []
    migrated_nodes = []

    # Local blocks are embedded in the workflow — they have no library namespace.
    # Collect their IDs so we don't try to resolve or mis-classify them.
    local_block_ids: set[str] = {
        lb.get("block_type_id", "")
        for lb in workflow.get("local_blocks", [])
    }

    for node in workflow.get("nodes", []):
        bid = node.get("block_type_id", "")
        new_bid = bid

        if "." not in bid and bid not in local_block_ids:
            # Try direct flat lookup
            if bid in _flat_index and _flat_index[bid]:
                new_bid = _flat_index[bid][0]   # prefer first (builtin)
            # Try forwarding alias
            elif bid in _forwarding_aliases:
                resolved = _forwarding_aliases[bid]
                new_bid = resolved
                redirects.append({"old_id": bid, "new_id": resolved})

        migrated_nodes.append({**node, "block_type_id": new_bid})

    # Collect library IDs only from successfully-namespaced block IDs (those with ".").
    # This prevents local-block IDs from being misidentified as library names.
    library_ids: list[str] = []
    seen: set[str] = set()
    for node in migrated_nodes:
        bid = node.get("block_type_id", "")
        if "." in bid:
            lib_id = bid.split(".")[0]
            if lib_id and lib_id not in seen:
                seen.add(lib_id)
                library_ids.append(lib_id)

    libraries_array = [
        {"id": "synapchart_builtin", "version": "1.0.0", "priority": 1}
    ]
    for i, lid in enumerate(library_ids):
        if lid != "synapchart_builtin":
            libraries_array.append({"id": lid, "version": "0.1.0", "priority": i + 2})

    migrated = {
        **workflow,
        "schema_version": "2.0",
        "libraries": libraries_array,
        "nodes": migrated_nodes,
    }
    return migrated, redirects


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def _check_missing_libraries(workflow: dict) -> list[dict]:
    """Return library declarations from the workflow that are not loaded.

    Also skips entries whose "id" is actually a block_type_id (can happen when
    a pre-fix migration accidentally placed local-block IDs in the libraries array).
    """
    from core.library_registry import _libraries, _flat_index
    # After load_workflow registers local blocks they appear in _flat_index.
    # A real library ID will never be a valid block short-ID.
    local_block_ids: set[str] = {
        lb.get("block_type_id", "")
        for lb in workflow.get("local_blocks", [])
    }
    missing: list[dict] = []
    for lib_entry in workflow.get("libraries", []):
        lid = lib_entry.get("id", "")
        if not lid:
            continue
        if lid in _libraries:
            continue
        # Guard: skip if this "library id" is actually a block type id.
        if lid in local_block_ids or lid in _flat_index:
            continue
        missing.append({
            "id":      lid,
            "version": lib_entry.get("version", ""),
            "name":    lid,
        })
    return missing


def _check_conflicts(workflow: dict) -> list[dict]:
    """Detect block ID conflicts across the workflow's declared libraries."""
    from core.library_registry import detect_conflicts
    library_ids = [lib["id"] for lib in workflow.get("libraries", []) if "id" in lib]
    return detect_conflicts(library_ids)


# ---------------------------------------------------------------------------
# Shared workflow processing helper
# ---------------------------------------------------------------------------

def _collect_all_node_types(fragment: dict) -> set[str]:
    """Return every block_type_id used as a node in *fragment* and all nested subflows."""
    types: set[str] = set()
    for node in fragment.get("nodes", []):
        types.add(node.get("block_type_id", ""))
    for cb in fragment.get("composite_blocks", []):
        subflow = cb.get("subflow", {})
        if subflow:
            types |= _collect_all_node_types(subflow)
    return types


def _process_workflow(workflow: dict, *, normalize_libraries: bool = False) -> tuple[dict, list[dict], bool, list[str]]:
    """Migrate schema, register blocks, and compute diagnostics.

    Returns:
        (workflow, forwarding_redirects, schema_migrated, composite_warnings)
    """
    forwarding_redirects: list[dict] = []
    schema_migrated = False
    composite_warnings: list[str] = []

    # Normalize libraries stored as plain strings (legacy template format)
    if normalize_libraries:
        raw_libs = workflow.get("libraries", [])
        if raw_libs and isinstance(raw_libs[0], str):
            workflow = {
                **workflow,
                "libraries": [{"id": lid, "version": "0.1.0", "priority": i + 1}
                              for i, lid in enumerate(raw_libs)],
            }

    # Schema migration: v1 → v2
    if workflow.get("schema_version", "1.0") != "2.0":
        workflow, forwarding_redirects = _migrate_v1_to_v2(workflow)
        schema_migrated = True

    # NOTE: local_blocks are intentionally NOT registered here.
    # They are workflow-private and only exist inside the workflow JSON.
    # The executor registers them at run time (PipelineExecutor.run).
    # Registering them here would pollute the global block registry and cause
    # workflow-embedded blocks to appear in the sidebar after a manual refresh.

    # Register composite blocks; surface any failures as warnings.
    # Only register composites that are actually referenced as node types
    # somewhere in this workflow (outer nodes or inside any subflow).
    # Orphaned legacy definitions in composite_blocks that are not used as
    # nodes anywhere must NOT be registered — they would pollute the global
    # block library sidebar without having a backing file on disk, causing
    # 404 errors when the user tries to drag them.
    used_block_types = _collect_all_node_types(workflow)
    for cb_def in workflow.get("composite_blocks", []):
        bid = cb_def.get("block_type_id", "")
        if bid not in used_block_types and f"user_blocks.{bid}" not in used_block_types:
            continue  # skip orphaned / unused composite definitions
        try:
            _register_composite(cb_def)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to register composite block '%s': %s", bid, exc)
            composite_warnings.append(f"Could not register composite block '{bid}': {exc}")

    # For packed workflows: auto-register embedded blocks for any library that
    # is not installed locally.  This makes packed workflows self-contained —
    # the recipient does not need to install the author's private libraries.
    if workflow.get("packed"):
        embedded = workflow.get("embedded_blocks", {})
        if embedded:
            from core.library_registry import _libraries
            missing_lib_ids = {
                lib["id"]
                for lib in workflow.get("libraries", [])
                if isinstance(lib, dict) and lib.get("id") not in _libraries
            }
            if missing_lib_ids:
                _register_embedded_blocks(embedded, missing_lib_ids)

    return workflow, forwarding_redirects, schema_migrated, composite_warnings


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/save")
async def save_workflow(request: SaveRequest) -> dict:
    """Save workflow JSON to a file path on disk."""
    target = Path(request.file_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(request.workflow, indent=2), encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail={
            "error": "save_failed",
            "message": f"Could not write to '{request.file_path}': {exc}",
            "details": {},
        })
    return {"status": "saved", "file_path": str(target)}


@router.post("/load")
async def load_workflow(request: LoadRequest) -> dict:
    """Load workflow JSON from disk.

    Returns the workflow (migrated to schema v2 if necessary) plus:
    - ``missing_libraries``: library IDs referenced by the workflow but not installed
    - ``conflicts``: short block IDs defined in more than one loaded library
    - ``forwarding_redirects``: blocks that were auto-resolved via forwarding aliases
    - ``schema_migrated``: true if the file was schema v1 and has been upgraded in memory
    - ``warnings``: non-fatal issues encountered during loading
    """
    target = Path(request.file_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail={
            "error": "file_not_found",
            "message": f"No file found at '{request.file_path}'.",
            "details": {},
        })

    try:
        workflow = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail={
            "error": "invalid_json",
            "message": f"File is not valid JSON: {exc}",
            "details": {},
        })

    workflow, forwarding_redirects, schema_migrated, warnings = _process_workflow(workflow)
    missing_libraries = _check_missing_libraries(workflow)
    conflicts         = _check_conflicts(workflow)

    return {
        "workflow":             workflow,
        "missing_libraries":    missing_libraries,
        "conflicts":            conflicts,
        "forwarding_redirects": forwarding_redirects,
        "schema_migrated":      schema_migrated,
        "warnings":             warnings,
    }


@router.get("/templates")
async def list_templates() -> dict:
    """List available template workflows grouped by category (subfolder).

    Returns a list of {name, category} objects, one per .json file found
    in any immediate subdirectory of the templates folder.
    """
    if not TEMPLATES_DIR.exists():
        return {"templates": []}
    templates = []
    for category_dir in sorted(TEMPLATES_DIR.iterdir()):
        if not category_dir.is_dir():
            continue
        for f in sorted(category_dir.glob("*.json")):
            templates.append({"name": f.stem, "category": category_dir.name})
    return {"templates": templates}


@router.get("/templates/{category}/{name}")
async def load_template(category: str, name: str) -> dict:
    """Load a named template workflow from a category subfolder.

    Applies the same schema migration and block-registration pipeline as
    POST /load so that v1 templates are upgraded and composite/local block
    definitions are available to the frontend immediately.
    """
    if not _SAFE_NAME_RE.match(category):
        raise HTTPException(status_code=422, detail={
            "error": "invalid_category_name",
            "message": f"'{category}' is not a valid category name.",
            "details": {},
        })
    if not _SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=422, detail={
            "error": "invalid_template_name",
            "message": f"'{name}' is not a valid template name.",
            "details": {},
        })

    template_path = TEMPLATES_DIR / category / f"{name}.json"
    if not template_path.exists():
        raise HTTPException(status_code=404, detail={
            "error": "template_not_found",
            "message": f"Template '{category}/{name}' does not exist.",
            "details": {},
        })

    try:
        workflow = json.loads(template_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail={
            "error": "invalid_json",
            "message": f"Template file is not valid JSON: {exc}",
            "details": {},
        })

    workflow, forwarding_redirects, schema_migrated, warnings = _process_workflow(
        workflow, normalize_libraries=True
    )
    missing_libraries = _check_missing_libraries(workflow)
    conflicts         = _check_conflicts(workflow)

    return {
        "workflow":             workflow,
        "template_path":        str(template_path),
        "missing_libraries":    missing_libraries,
        "conflicts":            conflicts,
        "forwarding_redirects": forwarding_redirects,
        "schema_migrated":      schema_migrated,
        "warnings":             warnings,
    }


# ---------------------------------------------------------------------------
# Embedded-block registration (packed workflow support)
# ---------------------------------------------------------------------------

def _register_embedded_blocks(embedded_blocks: dict, missing_lib_ids: set[str]) -> None:
    """Compile and register blocks from ``embedded_blocks`` for libraries that are
    not installed locally on this machine.

    Resolution policy: **missing-library fallback** — if the library IS installed
    locally, the local version is used and the embedded source is ignored.  This
    lets Alice benefit from bug-fixes she applied to her own copy of a shared
    library while still being able to run workflows that use libraries she has
    never installed.

    For Python blocks the embedded source is a full module file (including
    imports), so it can be exec'd directly into a fresh module object.
    For composite blocks the embedded definition JSON is registered via the
    normal _register_composite path.
    """
    import sys
    import types
    from blocks.base import BlockBase
    from core.library_registry import (
        register_block, _libraries, LibraryManifest, LEGACY_USER_DIR,
    )

    for block_type_id, entry in embedded_blocks.items():
        lib_id = entry.get("library_id", "")
        if not lib_id or lib_id not in missing_lib_ids:
            continue  # library is installed locally — use that version

        # Ensure a minimal manifest exists so register_block() can store metadata
        if lib_id not in _libraries:
            _libraries[lib_id] = LibraryManifest(
                id=lib_id,
                name=entry.get("library_name", lib_id),
                version=entry.get("library_version", "0.0.0"),
                path=LEGACY_USER_DIR,   # placeholder — no real folder on disk
                is_builtin=False,
            )

        block_type = entry.get("type", "python")

        if block_type == "python":
            source = entry.get("source_code", "")
            if not source:
                continue
            mod_name = f"_embedded_{lib_id}_{block_type_id.replace('.', '_')}"
            try:
                module = types.ModuleType(mod_name)
                module.__file__ = f"<embedded:{block_type_id}>"
                exec(compile(source, module.__file__, "exec"), module.__dict__)  # noqa: S102
                sys.modules[mod_name] = module
                for attr in vars(module).values():
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BlockBase)
                        and attr is not BlockBase
                        and getattr(attr, "block_type_id", "")
                    ):
                        register_block(attr(), lib_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to register embedded Python block '%s': %s", block_type_id, exc
                )

        elif block_type == "composite":
            definition = entry.get("definition", {})
            if not definition:
                continue
            try:
                _register_composite(definition)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to register embedded composite block '%s': %s", block_type_id, exc
                )

        # Recursively handle composite blocks' own embedded_blocks (inner subflow blocks)
        inner_embedded = entry.get("embedded_blocks", {})
        if inner_embedded:
            _register_embedded_blocks(inner_embedded, missing_lib_ids)


# ---------------------------------------------------------------------------
# Pack / Extract
# ---------------------------------------------------------------------------

def _embed_block(block_type_id: str) -> dict | None:
    """Build the embedded_blocks entry for one block."""
    from core.library_registry import _block_registry, _libraries
    block = _block_registry.get(block_type_id)
    if block is None:
        return None

    library_id = getattr(block, "_library_id", "")
    manifest   = _libraries.get(library_id)
    library_version = manifest.version if manifest else "0.0.0"

    if hasattr(block, "subflow"):  # CompositeBlockDefinition
        entry: dict = {
            "type":             "composite",
            "library_id":       library_id,
            "library_version":  library_version,
            "definition":       block.to_definition(),
            "subflow":          block.subflow,
        }
        # Recursively embed blocks used inside the subflow
        inner_ids = {n.get("block_type_id") for n in block.subflow.get("nodes", [])}
        inner_embedded = {}
        for inner_id in inner_ids:
            if inner_id:
                inner_entry = _embed_block(inner_id)
                if inner_entry:
                    inner_embedded[inner_id] = inner_entry
        if inner_embedded:
            entry["embedded_blocks"] = inner_embedded
        return entry

    # Python block — embed the entire source file (not just the class) so that
    # module-level imports are preserved when the source is re-executed on load.
    try:
        source_file = Path(inspect.getfile(type(block)))
        source = source_file.read_text(encoding="utf-8")
    except (OSError, TypeError):
        # Fallback: class-only source (imports will need to be injected at load time)
        try:
            source = inspect.getsource(type(block))
        except (OSError, TypeError):
            source = getattr(block, "_source_code", None) or ""

    return {
        "type":             "python",
        "library_id":       library_id,
        "library_version":  library_version,
        "definition":       block.to_definition(),
        "source_code":      source,
    }


@router.post("/pack")
async def pack_workflow(request: PackRequest) -> dict:
    """Pack a workflow into a self-contained JSON embedding all block sources.

    The packed file includes an ``embedded_blocks`` dict keyed by namespaced
    block_type_id, containing source code for Python blocks and full subflow
    definitions for composite blocks.
    """
    workflow = request.workflow
    node_ids = {n.get("block_type_id") for n in workflow.get("nodes", [])}

    embedded_blocks: dict = {}
    missing: list[str] = []
    for bid in sorted(node_ids):
        if not bid:
            continue
        entry = _embed_block(bid)
        if entry:
            embedded_blocks[bid] = entry
        else:
            missing.append(bid)

    packed = {
        **workflow,
        "packed":             True,
        "packed_at":          __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "embedded_blocks":    embedded_blocks,
    }

    target = Path(request.file_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(packed, indent=2), encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail={
            "error": "pack_failed",
            "message": f"Could not write packed file: {exc}",
            "details": {},
        })

    return {
        "status":          "packed",
        "file_path":       str(target),
        "embedded_count":  len(embedded_blocks),
        "missing_blocks":  missing,
    }


@router.post("/extract-block")
async def extract_block(request: ExtractBlockRequest) -> dict:
    """Extract one embedded block from a packed workflow into a user library.

    Writes the block's .py (or .json for composite) to the target library's
    blocks/ (or composite/) folder, then refreshes the library registry.
    """
    from core.library_registry import _libraries, refresh_user_libraries, USER_LIBRARY_ROOT

    target_manifest = _libraries.get(request.target_library_id)
    if target_manifest is None:
        raise HTTPException(status_code=404, detail={
            "error": "library_not_found",
            "message": f"Target library '{request.target_library_id}' is not loaded.",
            "details": {},
        })

    packed_path = Path(request.packed_workflow_path)
    if not packed_path.exists():
        raise HTTPException(status_code=404, detail={
            "error": "file_not_found",
            "message": f"Packed workflow not found at '{request.packed_workflow_path}'.",
            "details": {},
        })

    try:
        packed = json.loads(packed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail={
            "error": "invalid_json",
            "message": f"Packed workflow file is not valid JSON: {exc}",
            "details": {},
        })
    embedded = packed.get("embedded_blocks", {})
    entry = embedded.get(request.block_type_id)
    if entry is None:
        raise HTTPException(status_code=404, detail={
            "error": "block_not_embedded",
            "message": f"Block '{request.block_type_id}' is not embedded in this packed workflow.",
            "details": {},
        })

    flat_id = request.block_type_id.split(".", 1)[-1]

    if entry.get("type") == "composite":
        dest_dir = target_manifest.path / "composite"
        dest_dir.mkdir(parents=True, exist_ok=True)
        definition = {**entry.get("definition", {}), "block_type_id": flat_id}
        if "subflow" in entry:
            definition["subflow"] = entry["subflow"]
        dest_file = dest_dir / f"{flat_id}.json"
        dest_file.write_text(json.dumps(definition, indent=2), encoding="utf-8")
    else:
        dest_dir = target_manifest.path / "blocks"
        dest_dir.mkdir(parents=True, exist_ok=True)
        source = entry.get("source_code", "")
        dest_file = dest_dir / f"{flat_id}.py"
        dest_file.write_text(source, encoding="utf-8")

    refresh_user_libraries()

    return {
        "status":      "extracted",
        "block_type_id": request.block_type_id,
        "dest_path":   str(dest_file),
    }
