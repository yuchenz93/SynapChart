"""Plot decoded posterior examples for high-quality sleep pre/replay events.

Quality filter (configurable):
  • |weighted correlation| ≥ min_abs_wc  (default 0.6)
  • normalised max jump   ≤ max_norm_jump (default 0.4)

The ``epoch`` parameter controls which events to show:
  • "pre"   — only PREEpoch frames (preplay)
  • "post"  — only POSTEpoch frames (replay)
  • "both"  — all frames, with epoch label in the title

Each panel shows one frame × direction posterior heatmap with quality
metrics and epoch label in the title.
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


class PlotSleepReplayExamples(BlockBase):
    """Heatmap gallery of good-quality sleep pre/replay posteriors."""

    block_type_id = "plot_sleep_replay_examples"
    display_name  = "Plot Sleep Replay Examples"
    category      = "maze1d / Sleep"
    description   = (
        "Shows decoded posterior heatmaps for the best sleep pre/replay events. "
        "Frames are filtered by |wc| ≥ min_abs_wc and norm_max_jump ≤ max_norm_jump. "
        "Use the epoch parameter to show 'pre', 'post', or 'both'."
    )

    inputs = [
        PortDefinition("sleep_results", "NeuroData[sleep_results]",
                       "Output of decode_sleep_replay."),
    ]
    outputs: list = []
    parameters = [
        ParameterDefinition("epoch",         "enum:pre,post,both", "post",
                            "Which epoch to show: 'pre', 'post', or 'both'."),
        ParameterDefinition("min_abs_wc",    "float", 0.6,
                            "Minimum |weighted correlation| to qualify."),
        ParameterDefinition("max_norm_jump", "float", 0.4,
                            "Maximum normalised max jump to qualify."),
        ParameterDefinition("max_examples",  "int",   12,
                            "Maximum number of panels (sorted by |wc| desc)."),
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
        sr: NeuroData = inputs["sleep_results"]

        epoch_sel = str(parameters.get("epoch",         "post"))
        min_wc    = float(parameters.get("min_abs_wc",    0.6))
        max_nj    = float(parameters.get("max_norm_jump", 0.4))
        max_ex    = int(parameters.get("max_examples",    12))
        n_cols    = max(1, int(parameters.get("n_cols",   4)))
        cmap      = str(parameters.get("cmap",          "afmhot_r"))
        clim_val  = float(parameters.get("clim",         0.0))
        close_all = bool(parameters.get("close_all",     True))
        show      = bool(parameters.get("show_on_run",   True))
        save_path = str(parameters.get("save_path",      ""))

        if close_all:
            plt.close("all")

        results = sr.metadata.get("results", [])

        # ── Filter by epoch ───────────────────────────────────────────────────
        if epoch_sel in ("pre", "post"):
            pool = [r for r in results if r.get("epoch_label") == epoch_sel]
        else:
            pool = list(results)

        # ── Quality filter ────────────────────────────────────────────────────
        candidates = []
        for r in pool:
            wc = r.get("wc", np.nan)
            nj = r.get("norm_max_jump", np.nan)
            if np.isnan(wc) or np.isnan(nj):
                continue
            if abs(wc) >= min_wc and nj <= max_nj:
                candidates.append(r)

        candidates.sort(key=lambda r: abs(r.get("wc", 0.0)), reverse=True)
        candidates = candidates[:max_ex]

        if not candidates:
            fig, ax = plt.subplots(figsize=(6, 3))
            ep_str = {"pre": "preplay", "post": "replay"}.get(epoch_sel, "pre/post")
            ax.text(0.5, 0.5,
                    f"No {ep_str} frames passed quality filter\n"
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
                                hspace=0.50, wspace=0.35)

        for idx, rec in enumerate(candidates):
            row, col = divmod(idx, n_cols)
            ax = fig.add_subplot(gs[row, col])

            pdf      = np.asarray(rec.get("pdf", np.zeros((1, 1))), dtype=np.float64)
            t_bins   = np.asarray(rec.get("t_bins", []),     dtype=np.float64)
            bin_ctrs = np.asarray(rec.get("bin_centers", []), dtype=np.float64)

            if pdf.size == 0 or len(t_bins) == 0 or len(bin_ctrs) == 0:
                ax.text(0.5, 0.5, "No data", ha="center", va="center",
                        transform=ax.transAxes)
                continue

            t0, t1 = float(t_bins[0]),  float(t_bins[-1])
            y0, y1 = float(bin_ctrs[0]), float(bin_ctrs[-1])

            clim_up = clim_val if clim_val > 0 else float(np.percentile(pdf, 98))
            clim_up = max(clim_up, 1e-6)

            ax.imshow(
                pdf,
                aspect="auto", origin="lower",
                extent=[t0, t1, y0, y1],
                cmap=cmap, vmin=0.0, vmax=clim_up,
                interpolation="nearest",
            )

            wc          = rec.get("wc", np.nan)
            nj          = rec.get("norm_max_jump", np.nan)
            sig         = rec.get("is_sig", False)
            skey        = rec.get("state_key", "")
            ep_lbl      = rec.get("epoch_label", "?")
            t_dur       = (rec["t_end"] - rec["t_start"]) * 1000  # ms

            sig_str     = "SIG" if sig else "n.s."
            title_color = "#CC2222" if sig else "#555555"
            ep_tag = "Preplay" if ep_lbl == "pre" else "Replay"
            ax.set_title(
                f"{ep_tag}  {skey.split('_')[-1]}  [{t_dur:.0f} ms]  {sig_str}\n"
                f"wc={wc:.2f}  nj={nj:.2f}",
                fontsize=8.5, color=title_color, pad=3,
            )
            ax.set_xlabel("Time (s)", fontsize=8)
            ax.set_ylabel("Pos (cm)",  fontsize=8)
            ax.tick_params(labelsize=7)
            ax.set_xlim(t0, t1)
            ax.set_ylim(y0, y1)

        ep_str_title = {"pre": "Preplay", "post": "Replay"}.get(epoch_sel, "Pre/Replay")
        fig.suptitle(
            f"Sleep {ep_str_title} Examples  "
            f"(|wc| ≥ {min_wc:.2f}, norm_jump ≤ {max_nj:.2f}, n = {n_ex})",
            fontsize=12, y=1.02,
        )

        viz = save_and_encode(fig, save_path, show)
        plt.close(fig)
        return {"_viz": viz} if viz else {}
