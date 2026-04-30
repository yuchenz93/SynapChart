"""Plot significant waking-rest replay ratio vs 5 % chance level.

One bar per run direction with the overall fraction of significant frames
overlaid, plus a dashed line at the 5 % chance level.  Individual frame
wc values are optionally shown as a swarm/strip.
"""


from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from blocks.visualization import save_and_encode
from neurodata.types import NeuroData


class PlotReplayRatio(BlockBase):
    """Bar chart: significant replay fraction vs 5 % chance level."""

    block_type_id = "plot_replay_ratio"
    display_name  = "Plot Replay Ratio"
    category      = "maze1d / Waking Rest"
    description   = (
        "Shows the fraction of waking-rest frames that were classified as "
        "significant replay for each run direction, compared against the 5 % "
        "chance level.  Also shows the distribution of weighted-correlation "
        "values as a strip plot."
    )

    inputs = [
        PortDefinition("replay_results", "NeuroData[replay_results]",
                       "Output of decode_waking_rest_replay."),
    ]
    outputs: list = []
    parameters = [
        ParameterDefinition("chance_level",  "float", 0.05,
                            "Chance level reference line (default 5 %)."),
        ParameterDefinition("show_wc_strip", "bool",  True,
                            "Overlay individual weighted-correlation values as dots."),
        ParameterDefinition("close_all",     "bool",  True,  "Close existing figures."),
        ParameterDefinition("show_on_run",   "bool",  True,  "Show in viz panel."),
        ParameterDefinition("save_path",     "str",   "",    "PNG save path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        rr: NeuroData = inputs["replay_results"]

        chance     = float(parameters.get("chance_level",  0.05))
        show_strip = bool(parameters.get("show_wc_strip",  True))
        close_all  = bool(parameters.get("close_all",      True))
        show       = bool(parameters.get("show_on_run",    True))
        save_path  = str(parameters.get("save_path",       ""))

        if close_all:
            plt.close("all")

        results    = rr.metadata.get("results",           [])
        n_frames   = rr.metadata.get("n_frames",          0)
        n_repr     = rr.metadata.get("n_representations", 0) or n_frames
        n_sig      = rr.metadata.get("n_sig_frames",      0)
        sig_ratio  = rr.metadata.get("sig_ratio",         0.0)
        state_keys = rr.metadata.get("state_keys",        [])

        # ── Per-direction significant fractions ───────────────────────────────
        dir_data: dict[str, dict] = {}
        for skey in state_keys:
            recs = [r for r in results if r["state_key"] == skey]
            if not recs:
                continue
            n_total = len(set(r["frame_idx"] for r in results))  # total frames
            n_dir_sig  = sum(1 for r in recs if r["is_sig"])
            n_dir_all  = len(recs)
            wc_vals    = [r["wc"] for r in recs if not np.isnan(r.get("wc", np.nan))]
            dir_data[skey] = {
                "frac":    n_dir_sig / n_dir_all if n_dir_all > 0 else 0.0,
                "n_sig":   n_dir_sig,
                "n_total": n_dir_all,
                "wc_vals": wc_vals,
            }

        # ── Figure ────────────────────────────────────────────────────────────
        n_dirs = max(len(dir_data), 1)
        fig, axes = plt.subplots(1, 2, figsize=(4 + 3 * n_dirs, 5),
                                 gridspec_kw={"width_ratios": [n_dirs, n_dirs]})
        ax_bar, ax_wc = axes

        # --- Left panel: replay fraction bar ---------------------------------
        labels   = list(dir_data.keys())
        fracs    = [dir_data[k]["frac"] for k in labels]
        colors   = ["#E07070", "#7090D0", "#70C080", "#C080C0"][:n_dirs]

        xpos = np.arange(len(labels))
        ax_bar.bar(xpos, fracs, color=colors[:len(labels)], width=0.5,
                   edgecolor="k", linewidth=0.8, alpha=0.85, label="Sig. fraction")
        ax_bar.axhline(chance, color="k", linestyle="--", linewidth=1.5,
                       label=f"{int(chance*100):d}% chance level")

        # Overall ratio annotation
        ax_bar.text(len(labels) - 0.5, max(fracs + [chance]) * 1.12,
                    f"Overall:\n{sig_ratio:.1%}\n({n_sig}/{n_repr} repr.)",
                    ha="center", va="bottom", fontsize=10, color="#444")

        ax_bar.set_xticks(xpos)
        ax_bar.set_xticklabels([k.split("_")[-1] for k in labels], fontsize=11)
        ax_bar.set_ylabel("Fraction of significant frames", fontsize=12)
        ax_bar.set_ylim(0, min(1.0, max(fracs + [chance]) * 1.35))
        ax_bar.set_title("Significant Replay Ratio", fontsize=13)
        ax_bar.legend(fontsize=9, loc="upper right")
        ax_bar.spines[["top", "right"]].set_visible(False)

        # Counts on bars
        for xi, (lbl, frac) in enumerate(zip(labels, fracs)):
            n_s = dir_data[lbl]["n_sig"]
            n_t = dir_data[lbl]["n_total"]
            ax_bar.text(xi, frac + 0.005, f"{n_s}/{n_t}", ha="center",
                        va="bottom", fontsize=9)

        # --- Right panel: wc distribution ------------------------------------
        if show_strip and dir_data:
            rng = np.random.default_rng(0)
            for xi, lbl in enumerate(labels):
                wc_v = np.asarray(dir_data[lbl]["wc_vals"])
                if len(wc_v) == 0:
                    continue
                jitter = rng.uniform(-0.15, 0.15, size=len(wc_v))
                ax_wc.scatter(np.full(len(wc_v), xi) + jitter, wc_v,
                              s=18, alpha=0.5, color=colors[xi % len(colors)],
                              linewidths=0)
                # Mean line
                ax_wc.hlines(float(np.nanmean(wc_v)), xi - 0.25, xi + 0.25,
                             colors="k", linewidths=2)

            ax_wc.axhline(0, color="gray", linestyle=":", linewidth=1)
            ax_wc.set_xticks(np.arange(len(labels)))
            ax_wc.set_xticklabels([k.split("_")[-1] for k in labels], fontsize=11)
            ax_wc.set_ylabel("Weighted correlation", fontsize=12)
            ax_wc.set_ylim(-1.05, 1.05)
            ax_wc.set_title("Weighted Correlation Distribution", fontsize=13)
            ax_wc.spines[["top", "right"]].set_visible(False)
        else:
            ax_wc.set_visible(False)

        fig.tight_layout(pad=2.0)
        viz = save_and_encode(fig, save_path, show)
        plt.close(fig)
        return {"_viz": viz} if viz else {}
