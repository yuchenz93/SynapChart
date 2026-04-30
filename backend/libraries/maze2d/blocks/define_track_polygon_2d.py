"""Interactive GUI to define the maze track region as a 2D polygon.

Opens a matplotlib window showing all recorded x-y positions.  The user
clicks vertices with the left mouse button to draw the track boundary; the
polygon is closed by clicking near the first vertex.  On window close the
vertices are saved and returned.

On re-runs, paste the ``polygon_json`` string from the previous output into
the ``polygon_json`` parameter to skip the GUI entirely.

Output metadata layout::

    metadata["vertices"]     → list[[x, y], …]  polygon vertices in cm
    metadata["polygon_json"] → str  JSON string — paste into parameter for
                               future runs to skip the GUI
    metadata["n_vertices"]   → int
"""

from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


# ---------------------------------------------------------------------------
# Subprocess GUI script (written to a temp file and executed separately so
# the interactive Tkinter/Qt window runs in its own main thread).
# ---------------------------------------------------------------------------

_GUI_SCRIPT = r'''
import sys, json, numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.widgets import PolygonSelector

data_path = sys.argv[1]
out_path  = sys.argv[2]
pt_size   = float(sys.argv[3])
pt_alpha  = float(sys.argv[4])

pos_2d = np.load(data_path)   # (N, 2) cm

verts = []

fig, ax = plt.subplots(figsize=(9, 9))
ax.scatter(pos_2d[:, 0], pos_2d[:, 1],
           s=pt_size, alpha=pt_alpha, color='steelblue', linewidths=0,
           rasterized=True)
ax.set_xlabel('X (cm)', fontsize=12)
ax.set_ylabel('Y (cm)', fontsize=12)
ax.set_aspect('equal')
ax.set_title(
    'Draw track boundary polygon\n'
    'Left-click: add vertex   |   Click near start: close polygon   |   Close window: confirm',
    fontsize=11,
)
plt.tight_layout()

def on_select(v):
    # Called each time the polygon is updated / completed
    verts.clear()
    verts.extend(v)

sel = PolygonSelector(
    ax, on_select,
    useblit=True,
    props=dict(color='tomato', linewidth=1.5, linestyle='-', alpha=0.9),
    handle_props=dict(markersize=6, markerfacecolor='tomato'),
)
plt.show(block=True)

# Write result (may be empty if user closed before completing polygon)
with open(out_path, 'w') as fh:
    json.dump(verts, fh)
'''


class DefineTrackPolygon2d(BlockBase):
    """Interactive polygon definition for the 2D maze track region."""

    block_type_id = "define_track_polygon_2d"
    display_name  = "Define Track Polygon 2D"
    category      = "maze2d / Setup"
    description   = (
        "Opens an interactive matplotlib window showing all recorded 2D positions. "
        "The user draws a polygon around the valid track region by clicking vertices. "
        "On subsequent runs, paste the saved polygon_json into the parameter to skip "
        "the GUI."
    )

    inputs = [
        PortDefinition("position", "NeuroData[position]",
                       "Position data with two_d_location in metadata."),
    ]
    outputs = [
        PortDefinition("track_polygon", "NeuroData[track_polygon]",
                       "Polygon vertices defining the valid track region."),
    ]
    parameters = [
        ParameterDefinition("polygon_json", "str", "",
                            "JSON string of polygon vertices [[x,y],…] in cm. "
                            "If non-empty the GUI is skipped.  Copy from output "
                            "metadata after first interactive run."),
        ParameterDefinition("point_size",   "float", 0.5,
                            "Scatter point size for the position display."),
        ParameterDefinition("point_alpha",  "float", 0.2,
                            "Scatter point alpha for the position display."),
        ParameterDefinition("show_on_run",  "bool",  True,
                            "Show confirmation figure with polygon overlaid."),
        ParameterDefinition("save_path",    "str",   "",
                            "If non-empty, save confirmation figure to this path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        import json as _json

        pos_nd      = inputs["position"]
        polygon_str = str(parameters.get("polygon_json", "")).strip()
        pt_size     = float(parameters.get("point_size",  0.5))
        pt_alpha    = float(parameters.get("point_alpha", 0.2))
        show        = bool(parameters.get("show_on_run",  True))
        save_path   = str(parameters.get("save_path",    ""))

        # ── Extract 2D positions ──────────────────────────────────────────────
        pos_2d_raw = pos_nd.metadata.get("two_d_location")
        if pos_2d_raw is None:
            raise ValueError("define_track_polygon_2d: position has no two_d_location.")
        pos_2d_cm = np.asarray(pos_2d_raw, dtype=np.float64) * 100.0   # m → cm

        # ── Polygon source: GUI or pre-defined ────────────────────────────────
        if polygon_str:
            vertices = _json.loads(polygon_str)
        else:
            vertices = self._run_gui(pos_2d_cm, pt_size, pt_alpha)

        # ── Confirmation figure (always generated if show or save) ────────────
        viz = self._make_confirmation_figure(
            pos_2d_cm, vertices, pt_size, pt_alpha, save_path, show
        )

        polygon_json_out = _json.dumps(vertices)

        return {
            "track_polygon": NeuroData(
                data_type = "track_polygon",
                array     = np.array(vertices, dtype=np.float64) if vertices
                            else np.zeros((0, 2), dtype=np.float64),
                metadata  = {
                    "vertices":     vertices,
                    "polygon_json": polygon_json_out,
                    "n_vertices":   len(vertices),
                },
            ),
            "_viz": viz,
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _run_gui(pos_2d_cm: np.ndarray,
                 pt_size: float,
                 pt_alpha: float) -> list:
        """Spawn a subprocess GUI and return the collected polygon vertices."""
        import json as _json
        import os
        import subprocess
        import sys
        import tempfile

        # Save positions to a temp binary file readable by the subprocess
        tmp_data   = tempfile.mktemp(suffix=".npy")
        tmp_out    = tempfile.mktemp(suffix=".json")
        tmp_script = tempfile.mktemp(suffix=".py")

        try:
            np.save(tmp_data, pos_2d_cm)

            with open(tmp_script, "w") as f:
                f.write(_GUI_SCRIPT)

            subprocess.run(
                [sys.executable, tmp_script,
                 tmp_data, tmp_out,
                 str(pt_size), str(pt_alpha)],
                timeout=7200,   # 2-hour interactive timeout
            )

            if os.path.exists(tmp_out):
                with open(tmp_out) as f:
                    vertices = _json.load(f)
            else:
                vertices = []

        finally:
            for p in (tmp_data, tmp_out, tmp_script):
                try:
                    os.unlink(p)
                except OSError:
                    pass

        return vertices

    # ------------------------------------------------------------------
    @staticmethod
    def _make_confirmation_figure(
        pos_2d_cm: np.ndarray,
        vertices:  list,
        pt_size:   float,
        pt_alpha:  float,
        save_path: str,
        show:      bool,
    ) -> dict:
        """Scatter plot with the polygon overlaid; returns _viz dict."""
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon as MplPolygon

        fig, ax = plt.subplots(figsize=(7, 7))

        # All positions
        nan_mask = np.isnan(pos_2d_cm[:, 0]) | np.isnan(pos_2d_cm[:, 1])
        p = pos_2d_cm[~nan_mask]
        ax.scatter(p[:, 0], p[:, 1],
                   s=pt_size, alpha=pt_alpha, color="steelblue",
                   linewidths=0, rasterized=True, label="All positions")

        if vertices and len(vertices) >= 3:
            poly = MplPolygon(
                vertices, closed=True,
                edgecolor="tomato", facecolor="tomato",
                linewidth=1.5, alpha=0.15, label="Track polygon",
            )
            ax.add_patch(poly)
            vx = [v[0] for v in vertices]
            vy = [v[1] for v in vertices]
            ax.plot(vx + [vx[0]], vy + [vy[0]],
                    "-o", color="tomato", ms=5, lw=1.5, zorder=5)
            title = f"Track polygon — {len(vertices)} vertices"
        else:
            title = "No polygon defined (all positions included)"

        ax.set_xlabel("X (cm)", fontsize=12)
        ax.set_ylabel("Y (cm)", fontsize=12)
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=12)
        ax.legend(fontsize=9, loc="upper right")
        plt.tight_layout()

        return save_and_encode(fig, save_path, show)
