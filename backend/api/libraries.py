"""Library management endpoints.

GET  /api/libraries/              — list all discovered libraries
GET  /api/libraries/{id}          — get one library's metadata + block list
POST /api/libraries/refresh       — re-scan ~/.synapchart/blocklibrary/
POST /api/libraries/move-block    — move a block between libraries
GET  /api/libraries/conflicts     — detect conflicts across given library IDs
"""


from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.library_registry import (
    list_libraries, get_library_manifest, detect_conflicts,
    refresh_user_libraries, discover_all_libraries, all_blocks,
    BUILTIN_LIBRARY_ID, USER_LIBRARY_ROOT,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _library_to_dict(manifest) -> dict:
    return {
        "id":          manifest.id,
        "name":        manifest.name,
        "version":     manifest.version,
        "description": manifest.description,
        "author":      manifest.author,
        "is_builtin":  manifest.is_builtin,
        "path":        str(manifest.path),
    }


def _group_blocks_by_category(library_id: str) -> list[dict]:
    """Return [{name, blocks}] for a specific library."""
    prefix = f"{library_id}."
    by_cat: dict[str, list[dict]] = {}
    for block_id, block in all_blocks().items():
        if not block_id.startswith(prefix):
            continue
        defn = block.to_definition()
        defn["block_type_id"] = block_id   # ensure namespaced ID
        cat  = defn.get("category") or "Uncategorized"
        by_cat.setdefault(cat, []).append(defn)
    return [{"name": cat, "blocks": blks} for cat, blks in sorted(by_cat.items())]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
async def list_all_libraries() -> dict:
    """List all discovered libraries."""
    return {
        "libraries": [_library_to_dict(m) for m in list_libraries()]
    }


@router.get("/conflicts")
async def get_conflicts(library_ids: str = "") -> dict:
    """Detect block-ID conflicts across given comma-separated library IDs."""
    ids = [lid.strip() for lid in library_ids.split(",") if lid.strip()]
    if not ids:
        return {"conflicts": []}
    return {"conflicts": detect_conflicts(ids)}


@router.get("/{library_id}")
async def get_library(library_id: str) -> dict:
    """Get one library's metadata and its block list (grouped by category)."""
    try:
        manifest = get_library_manifest(library_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={
            "error": "library_not_found",
            "message": f"Library '{library_id}' is not loaded.",
            "details": {},
        })
    return {
        **_library_to_dict(manifest),
        "categories": _group_blocks_by_category(library_id),
    }


@router.post("/refresh")
async def refresh_libraries() -> dict:
    """Re-scan ~/.synapchart/blocklibrary/ without restarting the server."""
    refresh_user_libraries()
    return {
        "status": "refreshed",
        "libraries": [_library_to_dict(m) for m in list_libraries()],
    }


@router.post("/reload-all")
async def reload_all_libraries() -> dict:
    """Re-discover ALL libraries including built-in (full hot-reload)."""
    discover_all_libraries()
    return {
        "status": "reloaded",
        "libraries": [_library_to_dict(m) for m in list_libraries()],
    }


class MoveBlockRequest(BaseModel):
    block_type_id: str   # namespaced ID of the block to move
    target_library_id: str


@router.post("/move-block")
async def move_block(request: MoveBlockRequest) -> dict:
    """Move a block's file from its current library to another.

    Writes a forwarding alias to the source library's library.json.
    Only works for user libraries (built-in blocks cannot be moved).
    """
    from core.library_registry import _block_registry, _libraries, _forwarding_aliases

    block = _block_registry.get(request.block_type_id)
    if block is None:
        raise HTTPException(status_code=404, detail={
            "error": "block_not_found",
            "message": f"Block '{request.block_type_id}' is not registered.",
            "details": {},
        })

    src_library_id = getattr(block, "_library_id", None)
    if src_library_id == BUILTIN_LIBRARY_ID:
        raise HTTPException(status_code=403, detail={
            "error": "builtin_block",
            "message": "Built-in blocks cannot be moved.",
            "details": {},
        })

    src_manifest = _libraries.get(src_library_id)
    dst_manifest = _libraries.get(request.target_library_id)
    if dst_manifest is None:
        raise HTTPException(status_code=404, detail={
            "error": "library_not_found",
            "message": f"Target library '{request.target_library_id}' is not loaded.",
            "details": {},
        })

    # Find the source file
    flat_id   = request.block_type_id.split(".", 1)[1] if "." in request.block_type_id else request.block_type_id
    src_path  = src_manifest.path / f"{flat_id}.py" if src_manifest else None
    if src_path is None or not src_path.exists():
        raise HTTPException(status_code=404, detail={
            "error": "file_not_found",
            "message": f"Source file for '{flat_id}' not found.",
            "details": {},
        })

    # Move the file
    dst_blocks_dir = dst_manifest.path / "blocks"
    dst_blocks_dir.mkdir(parents=True, exist_ok=True)
    dst_path = dst_blocks_dir / src_path.name
    shutil.move(str(src_path), str(dst_path))

    # Write forwarding alias to source library.json
    if src_manifest:
        src_lib_json = src_manifest.path / "library.json"
        if src_lib_json.exists():
            with open(src_lib_json, encoding="utf-8") as f:
                lib_data = json.load(f)
        else:
            lib_data = {"id": src_library_id, "name": src_library_id, "version": "1.0.0"}
        aliases = lib_data.setdefault("forwarding_aliases", {})
        aliases[f"{src_library_id}.{flat_id}"] = f"{request.target_library_id}.{flat_id}"
        src_lib_json.write_text(json.dumps(lib_data, indent=2), encoding="utf-8")
        _forwarding_aliases[f"{src_library_id}.{flat_id}"] = f"{request.target_library_id}.{flat_id}"

    # Re-register the block under the new library
    refresh_user_libraries()

    return {
        "status": "moved",
        "old_id": request.block_type_id,
        "new_id": f"{request.target_library_id}.{flat_id}",
    }
