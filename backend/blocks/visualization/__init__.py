"""Shared utilities for all visualization blocks."""

import base64
import io
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # headless, no GUI required
import matplotlib.pyplot as plt


def save_and_encode(fig: plt.Figure, save_path: str, show_on_run: bool) -> dict:
    """Save a matplotlib figure to disk and/or encode it as base64.

    Args:
        fig:         The matplotlib Figure to output.
        save_path:   File path to save the PNG. Empty string skips saving.
        show_on_run: If True, encode the figure as a base64 PNG for the frontend.

    Returns:
        dict with optional keys ``saved_path`` and ``image_b64``.
    """
    result: dict = {}
    if save_path:
        out = Path(save_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out), bbox_inches="tight", dpi=150)
        result["saved_path"] = str(out)
    if show_on_run:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
        buf.seek(0)
        result["image_b64"] = "data:image/png;base64," + base64.b64encode(buf.read()).decode()
    plt.close(fig)
    return result
