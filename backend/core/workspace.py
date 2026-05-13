"""Workspace data serialization for the SynapChart debugger.

Summarizes cached node outputs into JSON-safe structures for the frontend
workspace panel and variable detail popup.
"""

from __future__ import annotations

import io
import base64

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from neurodata.types import NeuroData
from core.checkpoint import load_cache, has_cache


# ---------------------------------------------------------------------------
# Workspace summary
# ---------------------------------------------------------------------------

def summarize_outputs(node_id: str, cache_key: str) -> list[dict]:
    """Return a list of port summaries for one node's cached outputs.

    Each summary is JSON-safe and suitable for the workspace variable table.
    Returns an empty list if the cache file does not exist.
    """
    if not has_cache(cache_key):
        return []

    outputs = load_cache(cache_key)
    return [_summarize_value(port_id, value) for port_id, value in outputs.items()]


# Data types where channel_names is semantically "signal channel labels"
# (as opposed to cell IDs, bin labels, etc.)
_CHANNEL_NAME_TYPES = {"raw_signal", "lfp", "spike_matrix"}


def _summarize_value(port_id: str, value) -> dict:
    if isinstance(value, NeuroData):
        arr = value.array
        show_channel_names = value.data_type in _CHANNEL_NAME_TYPES
        return {
            "port_id":       port_id,
            "data_type":     f"NeuroData[{value.data_type}]",
            "shape":         list(arr.shape),
            "size":          int(arr.size),
            "dtype":         str(arr.dtype),
            "sampling_rate": value.sampling_rate,
            "n_channels":    arr.shape[1] if arr.ndim == 2 else 1,
            "n_samples":     arr.shape[0],
            "has_timestamps": value.timestamps is not None,
            "channel_names": value.channel_names if show_channel_names else None,
            "metadata_keys": list(value.metadata.keys()),
        }
    elif isinstance(value, np.ndarray):
        return {
            "port_id":   port_id,
            "data_type": "ndarray",
            "shape":     list(value.shape),
            "size":      int(value.size),
            "dtype":     str(value.dtype),
        }
    else:
        return {
            "port_id":       port_id,
            "data_type":     type(value).__name__,
            "shape":         None,
            "size":          1,
            "value_preview": str(value)[:200],
        }


# ---------------------------------------------------------------------------
# Variable detail (summary + statistics + truncated slice)
# ---------------------------------------------------------------------------

# Hard limits for detail views — prevents hanging on wide matrices like [80, 103376]
_MAX_DETAIL_ROWS = 500
_MAX_DETAIL_COLS = 50


def get_variable_detail(cache_key: str, port_id: str) -> dict:
    """Return full detail for one port output: summary + statistics + row slice.

    Both rows and columns are capped (_MAX_DETAIL_ROWS × _MAX_DETAIL_COLS) so
    that wide matrices (e.g. decoded posteriors with 100 k+ time bins) do not
    cause multi-second serialisation or frontend hangs.
    """
    outputs = load_cache(cache_key)
    value = outputs.get(port_id)

    if value is None:
        return {"error": f"Port '{port_id}' not found in cache."}

    if not isinstance(value, NeuroData):
        return {
            "summary":    _summarize_value(port_id, value),
            "statistics": None,
            "rows":       str(value),
        }

    arr = value.array
    summary = _summarize_value(port_id, value)

    # Build a 2-D view capped at _MAX_DETAIL_ROWS × _MAX_DETAIL_COLS
    if arr.ndim == 1:
        arr2d = arr[:_MAX_DETAIL_ROWS, np.newaxis]
    elif arr.ndim == 2:
        arr2d = arr[:_MAX_DETAIL_ROWS, :_MAX_DETAIL_COLS]
    else:
        arr2d = arr.reshape(arr.shape[0], -1)[:_MAX_DETAIL_ROWS, :_MAX_DETAIL_COLS]

    total_rows = arr.shape[0]
    total_cols = arr.shape[1] if arr.ndim >= 2 else 1
    shown_rows = arr2d.shape[0]
    shown_cols = arr2d.shape[1]

    stats = _compute_stats(arr2d)

    if arr.ndim >= 2:
        all_headers = (
            value.channel_names
            if value.channel_names and len(value.channel_names) == arr.shape[1]
            else [f"ch{i}" for i in range(arr.shape[1])]
        )
        col_headers = all_headers[:shown_cols]
    else:
        col_headers = ["value"]

    # Squeeze the newaxis back out for 1-D so data is [[v0], [v1], ...] → [v0, v1, ...]
    data = arr2d[:, 0].tolist() if arr.ndim == 1 else arr2d.tolist()

    rows = {
        "data":        data,
        "total_rows":  total_rows,
        "shown_rows":  shown_rows,
        "total_cols":  total_cols,
        "shown_cols":  shown_cols,
        "column_headers": col_headers,
    }

    return {
        "summary":    summary,
        "statistics": stats,
        "rows":       rows,
    }


def _compute_stats(arr: np.ndarray) -> list[dict]:
    """Compute per-channel descriptive statistics."""
    if arr.ndim == 1:
        arr2d = arr[:, np.newaxis]
    else:
        arr2d = arr

    stats = []
    for ch in range(arr2d.shape[1]):
        col = arr2d[:, ch]
        col_finite = col[np.isfinite(col)]
        stats.append({
            "channel": ch,
            "min":   float(np.min(col_finite))  if len(col_finite) else None,
            "max":   float(np.max(col_finite))  if len(col_finite) else None,
            "mean":  float(np.mean(col_finite)) if len(col_finite) else None,
            "std":   float(np.std(col_finite))  if len(col_finite) else None,
            "n_nan": int(np.sum(np.isnan(col))),
            "n_inf": int(np.sum(np.isinf(col))),
        })
    return stats


# ---------------------------------------------------------------------------
# Variable preview (base64 PNG plot)
# ---------------------------------------------------------------------------

_PREVIEW_MAX_SAMPLES = 5000


def get_variable_preview(cache_key: str, port_id: str) -> dict:
    """Return a base64 PNG preview plot for one port output.

    Plot type is chosen based on NeuroData.data_type.
    Returns {"error": ...} if the value is not a NeuroData instance.
    """
    outputs = load_cache(cache_key)
    value = outputs.get(port_id)

    if not isinstance(value, NeuroData):
        return {"error": "Preview only available for NeuroData outputs."}

    fig, ax = plt.subplots(figsize=(7, 3), dpi=100)

    try:
        _plot_neurodata(ax, value)
    except Exception as e:  # noqa: BLE001
        ax.text(0.5, 0.5, f"Preview error:\n{e}",
                ha="center", va="center", transform=ax.transAxes)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    image_b64 = base64.b64encode(buf.read()).decode()

    return {"image_b64": image_b64}


def _plot_neurodata(ax, value: NeuroData) -> None:
    arr = value.array
    dt  = value.data_type

    if dt in ("raw_signal", "lfp"):
        signal = arr[:, 0] if arr.ndim == 2 else arr
        label  = (value.channel_names[0] if value.channel_names else "ch0") if arr.ndim == 2 else "signal"
        t = (value.timestamps if value.timestamps is not None
             else np.arange(len(signal)) / (value.sampling_rate or 1.0))
        step = max(1, len(signal) // _PREVIEW_MAX_SAMPLES)
        ax.plot(t[::step], signal[::step], lw=0.8, label=label)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Amplitude")
        if arr.ndim == 2 and arr.shape[1] > 1:
            ax.set_title(f"Ch 0 of {arr.shape[1]} channels")

    elif dt == "spike_times":
        ax.eventplot(arr, lineoffsets=0.5, linelengths=0.8, color="black")
        ax.set_xlabel("Time (s)")
        ax.set_yticks([])
        ax.set_title("Spike times")

    elif dt == "spike_matrix":
        display = arr if arr.shape[1] <= _PREVIEW_MAX_SAMPLES else arr[:, ::arr.shape[1] // _PREVIEW_MAX_SAMPLES]
        ax.imshow(display, aspect="auto", origin="lower", interpolation="nearest")
        ax.set_xlabel("Time bin")
        ax.set_ylabel("Unit")
        ax.set_title("Spike matrix")

    elif dt == "position":
        if arr.ndim == 2 and arr.shape[1] >= 2:
            ax.plot(arr[:, 0], arr[:, 1], lw=0.8, alpha=0.7)
            ax.set_xlabel("X")
            ax.set_ylabel("Y")
            ax.set_title("Position trajectory")

    elif dt == "tuning_curve":
        ax.plot(arr.T if arr.ndim == 2 else arr, lw=1.2)
        ax.set_xlabel("Position bin")
        ax.set_ylabel("Firing rate (Hz)")
        ax.set_title("Tuning curve")

    elif dt == "decoded":
        step = max(1, arr.shape[1] // _PREVIEW_MAX_SAMPLES) if arr.ndim == 2 else 1
        display = arr[:, ::step] if arr.ndim == 2 else arr
        ax.imshow(display, aspect="auto", origin="lower", interpolation="nearest",
                  cmap="viridis")
        ax.set_xlabel("Time bin")
        ax.set_ylabel("Position bin")
        ax.set_title("Decoded posterior")

    else:
        flat = arr.flatten()[:_PREVIEW_MAX_SAMPLES]
        ax.plot(flat, lw=0.8)
        ax.set_title(f"NeuroData[{dt}] — raw values")
