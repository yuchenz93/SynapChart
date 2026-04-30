"""Plot decoded posterior examples for high-quality waking-rest replay events.

Quality filter (configurable):
  • |weighted correlation| ≥ min_abs_wc  (default 0.6)
  • normalised max jump   ≤ max_norm_jump (default 0.4)

Each panel shows one frame × direction posterior heatmap with:
  • animal position at the time of the frame (dashed blue line)
  • quality metrics in the title
"""


from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotReplayExamples(BlockBase):
    """Heatmap gallery of good-quality replay posteriors."""

    block_type_id = "plot_replay_examples"
    display_name  = "Plot Replay Examples"
    category      = "maze1d / Waking Rest"
    description   = (
        "Shows decoded posterior heatmaps for the best waking-rest replay events. "
        "Frames are filtered by |wc| ≥ min_abs_wc and norm_max_jump ≤ max_norm_jump. "
        "Each subplot shows one (frame, direction) pair with quality metrics in "
        "the title and animal position overlaid as a dashed line."
    )

    inputs = [
        PortDefinition("replay_results", "NeuroData[replay_results]",
                       "Output of decode_waking_rest_replay."),
        PortDefinition("position",       "NeuroData[position]",
                       "Linearised position (cm) — for animal-position overlay."),
    ]
    outputs: list = []
    parameters = [
        ParameterDefinition("min_abs_wc",    "float", 0.6,
                            "Minimum absolute weighted correlation to qualify as a "
                            "'good' replay example."),
        ParameterDefinition("max_norm_jump", "float", 0.4,
                            "Maximum normalised max jump (max_jump_cm / track_len) "
                            "to qualify as a good replay example."),
        ParameterDefinition("max_examples",  "int",   12,
                            "Maximum number of example panels to plot (sorted by "
                            "descending |wc|)."),
        ParameterDefinition("n_cols",        "int",   4,
                            "Number of columns in the example grid."),
        ParameterDefinition("cmap",          "str",   "afmhot_r",
                            "Colormap for posterior heatmaps."),
        ParameterDefinition("clim",          "float", 0.0,
                            "Colour scale upper limit (0 = auto)."),
        ParameterDefinition("close_all",     "bool",  True,  "Close existing figures."),
        ParameterDefinition("show_on_run",   "bool",  True,  "Show in viz panel."),
        ParameterDefinition("save_path",     "str",   "",    "PNG save path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        rr:  NeuroData = inputs["replay_results"]
        pos: NeuroData = inputs["position"]

        min_wc   = float(parameters.get("min_abs_wc",    0.6))
        max_nj   = float(parameters.get("max_norm_jump", 0.4))
        max_ex   = int(parameters.get("max_examples",    12))
        n_cols   = max(1, int(parameters.get("n_cols",   4)))
        cmap     = str(parameters.get("cmap",          "afmhot_r"))
        clim_val = float(parameters.get("clim",         0.0))
        close_all = bool(parameters.get("close_all",    True))
        show      = bool(parameters.get("show_on_run",  True))
        save_path = str(parameters.get("save_path",     ""))

        if close_all:
            plt.close("all")

        results     = rr.metadata.get("results", [])
        track_len   = float(rr.metadata.get("track_length_cm", 160.0))

        pos_1d = pos.array.flatten().astype(np.float64)
        pos_ts = pos.timestamps
        pos_sr = pos.sampling_rate or 39.0
        if pos_ts is None:
            pos_ts = np.arange(len(pos_1d)) / pos_sr

        # ── Filter and rank candidates ────────────────────────────────────────
        candidates = []
        for r in results:
            wc  = r.get("wc", np.nan)
            nj  = r.get("norm_max_jump", np.nan)
            if np.isnan(wc) or np.isnan(nj):
                continue
            if abs(wc) >= min_wc and nj <= max_nj:
                candidates.append(r)

        # Sort by |wc| descending
        candidates.sort(key=lambda r: abs(r.get("wc", 0.0)), reverse=True)
        candidates = candidates[:max_ex]

        if not candidates:
            fig, ax = plt.subplots(figsize=(6, 3))
            ax.text(0.5, 0.5,
                    f"No frames passed quality filter\n"
                    f"(|wc| ≥ {min_wc:.2f}, norm_jump ≤ {max_nj:.2f})",
                    ha="center", va="center", transform=ax.transAxes, fontsize=12)
            ax.axis("off")
            fig.tight_layout()
            viz = save_and_encode(fig, save_path, show)
            plt.close(fig)
            return {"_viz": viz} if viz else {}

        n_ex   = len(candidates)
        n_rows = int(np.ceil(n_ex / n_cols))

        fig = plt.figure(figsize=(n_cols * 3.5, n_rows * 3.8))
        gs  = gridspec.GridSpec(n_rows, n_cols, figure=fig,
                                hspace=0.45, wspace=0.35)

        for idx, rec in enumerate(candidates):
            row, col = divmod(idx, n_cols)
            ax = fig.add_subplot(gs[row, col])

            pdf        = np.asarray(rec.get("pdf", np.zeros((1, 1))), dtype=np.float64)
            t_bins     = np.asarray(rec.get("t_bins", []), dtype=np.float64)
            bin_ctrs   = np.asarray(rec.get("bin_centers", []), dtype=np.float64)

            if pdf.size == 0 or len(t_bins) == 0 or len(bin_ctrs) == 0:
                ax.text(0.5, 0.5, "No data", ha="center", va="center",
                        transform=ax.transAxes)
                continue

            t0, t1   = float(t_bins[0]),  float(t_bins[-1])
            y0, y1   = float(bin_ctrs[0]), float(bin_ctrs[-1])

            clim_up = clim_val if clim_val > 0 else float(np.percentile(pdf, 98))
            clim_up = max(clim_up, 1e-6)

            ax.imshow(
                pdf,
                aspect="auto", origin="lower",
                extent=[t0, t1, y0, y1],
                cmap=cmap, vmin=0.0, vmax=clim_up,
                interpolation="nearest",
            )

            # Animal position overlay
            pos_win = (pos_ts >= t0 - 0.05) & (pos_ts <= t1 + 0.05)
            if pos_win.any():
                ax.plot(pos_ts[pos_win], pos_1d[pos_win],
                        linestyle="--", linewidth=1.5, color="#4488FF", alpha=0.85)

            wc  = rec.get("wc", np.nan)
            nj  = rec.get("norm_max_jump", np.nan)
            sig = rec.get("is_sig", False)
            skey = rec.get("state_key", "")
            t_dur = (rec["t_end"] - rec["t_start"]) * 1000  # ms

            sig_str = "SIG" if sig else "n.s."
            title_color = "#CC2222" if sig else "#555555"
            ax.set_title(
                f"{skey.split('_')[-1]}  [{t_dur:.0f} ms]  {sig_str}\n"
                f"wc={wc:.2f}  nj={nj:.2f}",
                fontsize=8.5, color=title_color, pad=3,
            )
            ax.set_xlabel("Time (s)", fontsize=8)
            ax.set_ylabel("Pos (cm)",  fontsize=8)
            ax.tick_params(labelsize=7)
            ax.set_xlim(t0, t1)
            ax.set_ylim(y0, y1)

        fig.suptitle(
            f"Waking-Rest Replay Examples  "
            f"(|wc| ≥ {min_wc:.2f}, norm_jump ≤ {max_nj:.2f}, "
            f"n = {n_ex})",
            fontsize=12, y=1.02,
        )

        viz = save_and_encode(fig, save_path, show)
        plt.close(fig)
        return {"_viz": viz} if viz else {}
