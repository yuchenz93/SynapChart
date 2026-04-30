"""Per-node result cache for SynapChart pipelines."""

from __future__ import annotations

import hashlib

import json
import pickle
from pathlib import Path

from neurodata.types import NeuroData

CACHE_DIR = Path(".synapchart_cache")


def _make_key(
    node_id: str,
    block_type_id: str,
    parameters: dict,
    input_keys: list[str],
) -> str:
    """Compute a deterministic cache key from node identity and upstream keys.

    Changing any parameter or any upstream cache key produces a different key,
    automatically invalidating this node and all of its descendants.

    Args:
        node_id:       The node's unique ID (included for human-readable context
                       in debugging; does not affect invalidation logic).
        block_type_id: The block implementation identifier.
        parameters:    The node's current parameter dict.
        input_keys:    Cache keys of all direct predecessor nodes.

    Returns:
        A 16-character hex string used as the on-disk filename stem.
    """
    payload = json.dumps(
        {
            "block_type_id": block_type_id,
            "parameters": parameters,
            "input_keys": sorted(input_keys),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def has_cache(cache_key: str) -> bool:
    """Return True if a cached result exists for cache_key.

    Args:
        cache_key: Key returned by :func:`_make_key`.
    """
    return (CACHE_DIR / f"{cache_key}.pkl").exists()


def load_cache(cache_key: str) -> dict[str, NeuroData]:
    """Load and return cached block outputs.

    Args:
        cache_key: Key returned by :func:`_make_key`.

    Returns:
        Dict mapping output port_id -> NeuroData (or primitive).

    Raises:
        FileNotFoundError: If no cache file exists for this key.
    """
    cache_file = CACHE_DIR / f"{cache_key}.pkl"
    with cache_file.open("rb") as fh:
        return pickle.load(fh)  # noqa: S301


def save_cache(cache_key: str, outputs: dict[str, NeuroData]) -> None:
    """Persist block outputs to the cache directory.

    Args:
        cache_key: Key returned by :func:`_make_key`.
        outputs:   Dict mapping output port_id -> NeuroData (or primitive).
    """
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}.pkl"
    with cache_file.open("wb") as fh:
        pickle.dump(outputs, fh)


def clear_cache(node_cache_key: str | None = None) -> int:
    """Remove cached files from disk.

    Args:
        node_cache_key: If given, delete only the file for this specific key.
                        If None, delete all cached files.

    Returns:
        Number of files deleted.
    """
    if not CACHE_DIR.exists():
        return 0

    if node_cache_key is not None:
        target = CACHE_DIR / f"{node_cache_key}.pkl"
        if target.exists():
            target.unlink()
            return 1
        return 0

    count = 0
    for f in CACHE_DIR.glob("*.pkl"):
        f.unlink()
        count += 1
    return count
