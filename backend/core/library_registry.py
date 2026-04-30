"""Library-aware block registry.

Replaces the flat ``core.block_registry`` with a namespaced system.
Each block is stored as ``{library_id}.{block_type_id}`` (the *namespaced ID*).

Backward compatibility
----------------------
``get_block()`` accepts both namespaced IDs (``synapchart_builtin.bandpass_filter``)
and legacy flat IDs (``bandpass_filter``).  Flat IDs are resolved via
``_flat_index`` which maps short names → [namespaced IDs], preferring the
built-in library when multiple libraries define the same short name.
"""


from __future__ import annotations

import importlib
import importlib.util as _ilu
import json
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

import blocks as _blocks_pkg
from blocks.base import BlockBase, CompositeBlockDefinition

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BACKEND_DIR        = Path(__file__).resolve().parent.parent
BUILTIN_LIBRARY_PATH = _BACKEND_DIR / "builtin_library"
_BLOCKS_PKG_DIR      = _BACKEND_DIR / "blocks"
LEGACY_USER_DIR      = _BLOCKS_PKG_DIR / "user"
LEGACY_COMPOSITE_DIR = _BLOCKS_PKG_DIR / "composite"
BUNDLED_LIBRARIES_DIR = _BACKEND_DIR / "libraries"
USER_LIBRARY_ROOT    = Path.home() / ".synapchart" / "blocklibrary"

BUILTIN_LIBRARY_ID    = "synapchart_builtin"
USER_BLOCKS_LIBRARY_ID = "user_blocks"

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class LibraryManifest:
    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    group: str = ""          # Optional display group (e.g. "Electrophysiology Analysis")
    path: Path = field(default_factory=Path)
    is_builtin: bool = False
    synapchart_min_version: str = ""
    forwarding_aliases: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Registry state
# ---------------------------------------------------------------------------

_libraries: dict[str, LibraryManifest] = {}
_block_registry: dict[str, Union[BlockBase, CompositeBlockDefinition]] = {}
_forwarding_aliases: dict[str, str] = {}
# flat short_id → list of namespaced IDs (for conflict detection + flat lookup)
_flat_index: dict[str, list[str]] = {}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_all_libraries() -> None:
    """Load all libraries. Called once at application startup."""
    _libraries.clear()
    _block_registry.clear()
    _forwarding_aliases.clear()
    _flat_index.clear()

    _load_builtin_library()
    _load_bundled_libraries()
    _load_legacy_user_blocks()
    _load_legacy_composite_blocks()
    _load_external_user_libraries()


def _read_manifest(path: Path, is_builtin: bool = False) -> LibraryManifest:
    manifest_path = path / "library.json"
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        return LibraryManifest(
            id=data["id"],
            name=data.get("name", data["id"]),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            group=data.get("group", ""),
            path=path,
            is_builtin=is_builtin,
            synapchart_min_version=data.get("synapchart_min_version", ""),
            forwarding_aliases=data.get("forwarding_aliases", {}),
        )
    # Fallback manifest when library.json is missing
    return LibraryManifest(
        id=BUILTIN_LIBRARY_ID if is_builtin else path.name,
        name="Neural Analysis Core" if is_builtin else path.name,
        version="1.0.0",
        path=path,
        is_builtin=is_builtin,
    )


def _register_manifest(manifest: LibraryManifest) -> None:
    _libraries[manifest.id] = manifest
    for old_id, new_id in manifest.forwarding_aliases.items():
        _forwarding_aliases[old_id] = new_id


def _register_instance(
    instance: Union[BlockBase, CompositeBlockDefinition],
    library_id: str,
) -> None:
    """Register a block instance with the given library namespace."""
    flat_id = instance.block_type_id
    namespaced_id = f"{library_id}.{flat_id}"
    # Attach library metadata to the instance for later reference
    object.__setattr__(instance, "_library_id", library_id) if hasattr(instance, "__dict__") else None
    try:
        instance._library_id = library_id       # type: ignore[attr-defined]
        instance._namespaced_id = namespaced_id # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        pass
    _block_registry[namespaced_id] = instance
    _flat_index.setdefault(flat_id, []).append(namespaced_id)


def _load_builtin_library() -> None:
    manifest = _read_manifest(BUILTIN_LIBRARY_PATH, is_builtin=True)
    _register_manifest(manifest)

    # Walk blocks/ package via pkgutil; skip user/ and composite/ sub-packages
    for _finder, name, _ispkg in pkgutil.walk_packages(
        _blocks_pkg.__path__, prefix="blocks."
    ):
        if "blocks.user" in name or "blocks.composite" in name:
            continue
        try:
            module = importlib.import_module(name)
        except Exception:  # noqa: BLE001
            continue
        for attr in vars(module).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, BlockBase)
                and attr is not BlockBase
                and getattr(attr, "block_type_id", "")
            ):
                _register_instance(attr(), BUILTIN_LIBRARY_ID)


def _load_bundled_libraries() -> None:
    """Load domain libraries shipped inside backend/libraries/."""
    if not BUNDLED_LIBRARIES_DIR.exists():
        return
    for entry in sorted(BUNDLED_LIBRARIES_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if not (entry / "library.json").exists():
            continue
        try:
            manifest = _read_manifest(entry, is_builtin=True)
            _register_manifest(manifest)
            blocks_dir = entry / "blocks"
            if blocks_dir.exists():
                _load_py_files_from_dir(blocks_dir, manifest.id)
            composite_dir = entry / "composite"
            if composite_dir.exists():
                _load_composite_files_from_dir(composite_dir, manifest.id)
        except Exception:  # noqa: BLE001
            pass


def _load_legacy_user_blocks() -> None:
    """Load blocks from backend/blocks/user/ as the 'user_blocks' library."""
    if not LEGACY_USER_DIR.exists():
        return
    _libraries.setdefault(
        USER_BLOCKS_LIBRARY_ID,
        LibraryManifest(
            id=USER_BLOCKS_LIBRARY_ID,
            name="User Blocks",
            version="1.0.0",
            description="Custom blocks created via the block editor.",
            path=LEGACY_USER_DIR,
            is_builtin=False,
        ),
    )
    _load_py_files_from_dir(LEGACY_USER_DIR, USER_BLOCKS_LIBRARY_ID)


def _load_legacy_composite_blocks() -> None:
    """Load composite JSONs from backend/blocks/composite/ under user_blocks.

    These are blocks created via the packaging wizard, so they belong to the
    user_blocks library — the same library that register_block() assigns them
    to at runtime when package_block() calls _register_composite().
    Keeping the library consistent means the namespaced ID is always
    'user_blocks.<short_id>' regardless of whether the block was loaded at
    startup or registered in the same server session.
    """
    if not LEGACY_COMPOSITE_DIR.exists():
        return
    # Ensure the user_blocks manifest exists (normally created by _load_legacy_user_blocks,
    # but we guard here in case the user/ dir is absent or ordering ever changes).
    _libraries.setdefault(
        USER_BLOCKS_LIBRARY_ID,
        LibraryManifest(
            id=USER_BLOCKS_LIBRARY_ID,
            name="User Blocks",
            version="1.0.0",
            description="Custom blocks created via the block editor.",
            path=LEGACY_USER_DIR,
            is_builtin=False,
        ),
    )
    _load_composite_files_from_dir(LEGACY_COMPOSITE_DIR, USER_BLOCKS_LIBRARY_ID)


def _load_external_user_libraries() -> None:
    """Walk ~/.synapchart/blocklibrary/ and load each sub-folder as a library."""
    if not USER_LIBRARY_ROOT.exists():
        return
    for entry in sorted(USER_LIBRARY_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        manifest_path = entry / "library.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = _read_manifest(entry)
            _register_manifest(manifest)
            blocks_dir = entry / "blocks"
            if blocks_dir.exists():
                _load_py_files_from_dir(blocks_dir, manifest.id)
            composite_dir = entry / "composite"
            if composite_dir.exists():
                _load_composite_files_from_dir(composite_dir, manifest.id)
        except Exception:  # noqa: BLE001
            pass


def _load_py_files_from_dir(directory: Path, library_id: str) -> None:
    """Load BlockBase subclasses from individual .py files in a flat directory."""
    for py_file in sorted(directory.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            spec = _ilu.spec_from_file_location(
                f"_nf_lib_{library_id}_{py_file.stem}", py_file
            )
            if spec is None or spec.loader is None:
                continue
            module = _ilu.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[arg-type]
            import sys as _sys
            _sys.modules[module.__name__] = module
            for attr in vars(module).values():
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BlockBase)
                    and attr is not BlockBase
                    and getattr(attr, "block_type_id", "")
                ):
                    _register_instance(attr(), library_id)
        except Exception:  # noqa: BLE001
            pass


def _load_composite_files_from_dir(directory: Path, library_id: str) -> None:
    """Load CompositeBlockDefinition objects from .json files in a directory."""
    for json_file in sorted(directory.glob("*.json")):
        try:
            with open(json_file, encoding="utf-8") as f:
                definition = json.load(f)
            flat_id = definition.get("block_type_id", "")
            if not flat_id:
                continue
            instance = CompositeBlockDefinition(definition)
            _register_instance(instance, library_id)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_block(block_type_id: str) -> Union[BlockBase, CompositeBlockDefinition]:
    """Resolve a block by namespaced or flat ID.

    Resolution order:
    1. Direct match in ``_block_registry`` (namespaced preferred)
    2. Forwarding alias resolution
    3. Flat ID lookup via ``_flat_index`` (prefers builtin library)

    Raises KeyError with a helpful message if the block is not found.
    """
    if block_type_id in _block_registry:
        return _block_registry[block_type_id]

    # Forwarding alias
    if block_type_id in _forwarding_aliases:
        resolved = _forwarding_aliases[block_type_id]
        if resolved in _block_registry:
            return _block_registry[resolved]

    # Flat ID → prefer builtin, then first registered
    if block_type_id in _flat_index:
        candidates = _flat_index[block_type_id]
        # Prefer builtin
        for nid in candidates:
            if nid.startswith(f"{BUILTIN_LIBRARY_ID}."):
                return _block_registry[nid]
        if candidates:
            return _block_registry[candidates[0]]

    raise KeyError(
        f"Block '{block_type_id}' not found. "
        f"Is the library installed and included in this workflow?"
    )


def all_blocks() -> dict[str, Union[BlockBase, CompositeBlockDefinition]]:
    """Return a shallow copy of the registry (namespaced keys only)."""
    # Filter to namespaced IDs only (exclude any legacy flat-ID entries)
    return {k: v for k, v in _block_registry.items() if "." in k}


def list_libraries() -> list[LibraryManifest]:
    """Return all loaded library manifests, built-in first."""
    builtins = [m for m in _libraries.values() if m.is_builtin]
    others   = sorted(
        [m for m in _libraries.values() if not m.is_builtin],
        key=lambda m: m.name.lower(),
    )
    return builtins + others


def get_library_manifest(library_id: str) -> LibraryManifest:
    if library_id not in _libraries:
        raise KeyError(f"Library '{library_id}' is not loaded.")
    return _libraries[library_id]


def detect_conflicts(library_ids: list[str]) -> list[dict]:
    """Return short IDs that appear in more than one of the given libraries."""
    conflicts: list[dict] = []
    for flat_id, namespaced_ids in _flat_index.items():
        matching = [nid for nid in namespaced_ids if nid.split(".")[0] in library_ids]
        if len(matching) > 1:
            found_in = [nid.split(".")[0] for nid in matching]
            # Determine resolution by priority (first library listed wins)
            priority_map = {lid: i for i, lid in enumerate(library_ids)}
            resolved_lib = min(found_in, key=lambda lid: priority_map.get(lid, 999))
            conflicts.append({
                "short_id":   flat_id,
                "found_in":   found_in,
                "resolved_to": f"{resolved_lib}.{flat_id}",
                "resolution": "priority",
            })
    return conflicts


def register_block(
    block: Union[BlockBase, CompositeBlockDefinition],
    library_id: str | None = None,
) -> None:
    """Register a block at runtime (used for custom/composite blocks).

    If ``library_id`` is given, the block is namespaced under it.
    If the block's ``block_type_id`` already contains a dot it is stored as-is.
    Otherwise defaults to ``user_blocks``.
    """
    flat_id = block.block_type_id

    if "." in flat_id:
        # Already namespaced — store directly under that key
        namespaced_id = flat_id
        _block_registry[namespaced_id] = block
        short_id = flat_id.split(".", 1)[1]
        _flat_index.setdefault(short_id, [])
        if namespaced_id not in _flat_index[short_id]:
            _flat_index[short_id].append(namespaced_id)
        return

    lib = library_id or USER_BLOCKS_LIBRARY_ID
    if lib not in _libraries:
        _libraries[lib] = LibraryManifest(
            id=lib, name="User Blocks", version="1.0.0",
            path=LEGACY_USER_DIR, is_builtin=False,
        )

    namespaced_id = f"{lib}.{flat_id}"
    try:
        block._library_id   = lib            # type: ignore[attr-defined]
        block._namespaced_id = namespaced_id  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        pass

    _block_registry[namespaced_id] = block
    # Also register under flat ID for backward-compat lookup paths
    _block_registry[flat_id] = block
    _flat_index.setdefault(flat_id, [])
    if namespaced_id not in _flat_index[flat_id]:
        _flat_index[flat_id].insert(0, namespaced_id)  # prepend so it wins flat lookup


def unregister_block(block_type_id: str) -> None:
    """Remove a block from the registry (used when deleting custom blocks)."""
    block = _block_registry.pop(block_type_id, None)
    namespaced = getattr(block, "_namespaced_id", None) if block else None

    if namespaced and namespaced != block_type_id:
        _block_registry.pop(namespaced, None)

    # Determine short ID for flat_index cleanup
    short_id = block_type_id.split(".", 1)[1] if "." in block_type_id else block_type_id
    remove_nid = namespaced or block_type_id
    if short_id in _flat_index:
        _flat_index[short_id] = [n for n in _flat_index[short_id] if n != remove_nid]
        if not _flat_index[short_id]:
            del _flat_index[short_id]

    # Clean up flat ID entry if it pointed to the same block
    if short_id in _block_registry:
        existing = _block_registry[short_id]
        if getattr(existing, "_namespaced_id", None) == remove_nid:
            del _block_registry[short_id]


def refresh_user_libraries() -> None:
    """Re-scan ~/.synapchart/blocklibrary/ without touching the built-in library."""
    # Remove all non-builtin, non-user_blocks libraries from state
    to_remove = [lid for lid, m in _libraries.items() if not m.is_builtin and lid != USER_BLOCKS_LIBRARY_ID]
    for lib_id in to_remove:
        prefix = f"{lib_id}."
        for key in [k for k in _block_registry if k.startswith(prefix)]:
            del _block_registry[key]
        for flat_id in list(_flat_index.keys()):
            _flat_index[flat_id] = [n for n in _flat_index[flat_id] if not n.startswith(prefix)]
            if not _flat_index[flat_id]:
                del _flat_index[flat_id]
        del _libraries[lib_id]

    _load_external_user_libraries()
