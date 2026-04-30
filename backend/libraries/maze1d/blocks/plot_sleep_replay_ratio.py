"""Plot significant sleep pre/replay ratio vs 5 % chance level.

Two groups (PRE = preplay, POST = replay) are shown side by side, each
with per-direction bars.  A plasticity annotation shows the Fisher-exact
p-value for POST > PRE significance.  Individual wc values are shown as
a strip plot on the right.
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


class PlotSleepReplayRatio(BlockBase):
    """Bar chart: pre/replay significant fraction vs 5 % chance level."""

    block_type_id = "plot_sleep_replay_ratio"
    display_name  = "Plot Sleep Replay Ratio"
    category      = "maze1d / Sleep"
    description   = (
        "Shows the fraction of sleep frames (pre-run and post-run) classified as "
        "significant replay for each run direction compared to the 5 % chance "
        "level.  Also shows wc distribution and plasticity test (POST > PRE)."
    )

    inputs = [
        PortDefinition("sleep_results", "NeuroData[sleep_results]",
                       "Output of decode_sleep_replay."),
    ]
    outputs: list = []
    parameters = [
        ParameterDefinition("chance_level",  "float", 0.05,
                            "Chance level reference line (default 5 %)."),
        ParameterDefinition("show_wc_strip", "bool",  True,
                            "Overlay individual wc values as dots."),
        ParameterDefinition("close_all",     "bool",  True,  "Close existing figures."),
        ParameterDefinition("show_on_run",   "bool",  True,  "Show in viz panel."),
        ParameterDefinition("save_path",     "str",   "",    "PNG save path."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        sr: NeuroData = inputs["sleep_results"]

        chance     = float(parameters.get("chance_level",  0.05))
        show_strip = bool(parameters.get("show_wc_strip",  True))
        close_all  = bool(parameters.get("close_all",      True))
        show       = bool(parameters.get("show_on_run",    True))
        save_path  = str(parameters.get("save_path",       ""))

        if close_all:
            plt.close("all")

        results    = sr.metadata.get("results",              [])
        state_keys = sr.metadata.get("state_keys",           [])

        n_repr_pre   = sr.metadata.get("n_representations_pre",  0)
        n_repr_post  = sr.metadata.get("n_representations_post", 0)
        n_sig_pre    = sr.metadata.get("n_sig_pre",              0)
        n_sig_post   = sr.metadata.get("n_sig_post",             0)
        sig_ratio_pre  = sr.metadata.get("sig_ratio_pre",  0.0)
        sig_ratio_post = sr.metadata.get("sig_ratio_post", 0.0)
        pval           = sr.metadata.get("plasticity_pvalue", np.nan)

        # ── Per-direction × epoch data ─────────────────────────────────────────
        # key: (epoch_label, state_key)
        dir_data: dict[tuple, dict] = {}
        for skey in state_keys:
            for ep_lbl in ("pre", "post"):
                recs = [r for r in results
                        if r["state_key"] == skey and r["epoch_label"] == ep_lbl]
                if not recs:
                    continue
                n_s   = sum(1 for r in recs if r["is_sig"])
                n_t   = len(recs)
                wc_v  = [r["wc"] for r in recs if not np.isnan(r.get("wc", np.nan))]
                dir_data[(ep_lbl, skey)] = {
                    "frac":    n_s / n_t if n_t > 0 else 0.0,
                    "n_sig":   n_s,
                    "n_total": n_t,
                    "wc_vals": wc_v,
                }

        # Axis layout: one group per epoch, subdivided by direction
        n_dirs  = len(state_keys)
        n_groups = 2   # PRE and POST

        fig, axes = plt.subplots(1, 2, figsize=(4 + 3 * n_groups * n_dirs, 5),
                                 gridspec_kw={"width_ratios": [1, 1]})
        ax_bar, ax_wc = axes

        # Colours: warm palette for PRE, cool for POST
        pre_colors  = ["#E07070", "#E09050", "#D0A070", "#C07050"]
        post_colors = ["#7090D0", "#5070C0", "#4080B0", "#5090A0"]

        # x-positions: PRE group then POST group, with small gap
        group_gap = 0.4
        bar_w     = 0.35
        pre_xs  = np.arange(n_dirs) * (bar_w + 0.05)
        post_xs = pre_xs + n_dirs * (bar_w + 0.05) + group_gap

        all_xs_mid = np.concatenate([pre_xs, post_xs])
        all_fracs  = []
        tick_xs    = []
        tick_lbls  = []

        for gi, (epoch_label, xs, colors) in enumerate(
            [("pre", pre_xs, pre_colors), ("post", post_xs, post_colors)]
        ):
            for di, skey in enumerate(state_keys):
                key  = (epoch_label, skey)
                data = dir_data.get(key, {"frac": 0.0, "n_sig": 0, "n_total": 0,
                                          "wc_vals": []})
                frac = data["frac"]
                all_fracs.append(frac)
                col  = colors[di % len(colors)]

                ax_bar.bar(xs[di], frac, width=bar_w, color=col,
                           edgecolor="k", linewidth=0.8, alpha=0.85)
                ax_bar.text(xs[di], frac + 0.005,
                            f"{data['n_sig']}/{data['n_total']}",
                            ha="center", va="bottom", fontsize=8)
                tick_xs.append(xs[di])
                short = skey.split("_")[-1]
                tick_lbls.append(f"{'Pre' if epoch_label == 'pre' else 'Post'}\n{short}")

        # Chance level
        ax_bar.axhline(chance, color="k", linestyle="--", linewidth=1.5,
                       label=f"{int(chance * 100):d}% chance")

        # PRE / POST overall annotation
        y_top = max(all_fracs + [chance]) if all_fracs else chance
        ax_bar.text(np.mean(pre_xs),  y_top * 1.25,
                    f"PRE: {sig_ratio_pre:.1%}\n({n_sig_pre}/{n_repr_pre})",
                    ha="center", va="bottom", fontsize=9, color="#883333")
        ax_bar.text(np.mean(post_xs), y_top * 1.25,
                    f"POST: {sig_ratio_post:.1%}\n({n_sig_post}/{n_repr_post})",
                    ha="center", va="bottom", fontsize=9, color="#2244AA")

        # Plasticity annotation
        if not np.isnan(pval):
            sig_sym = "***" if pval < 0.001 else ("**" if pval < 0.01 else
                       ("*" if pval < 0.05 else "n.s."))
            ax_bar.text(np.mean(all_xs_mid), y_top * 1.45,
                        f"POST > PRE: p={pval:.3g}  {sig_sym}",
                        ha="center", va="bottom", fontsize=10,
                        color="#115511" if pval < 0.05 else "#555555")

        ax_bar.set_xticks(tick_xs)
        ax_bar.set_xticklabels(tick_lbls, fontsize=9)
        ax_bar.set_ylabel("Fraction significant", fontsize=12)
        ax_bar.set_ylim(0, min(1.0, y_top * 1.6))
        ax_bar.set_title("Sleep Pre/Replay Ratio", fontsize=13)
        ax_bar.legend(fontsize=9, loc="upper left")
        ax_bar.spines[["top", "right"]].set_visible(False)

        # ── WC strip panel ────────────────────────────────────────────────────
        if show_strip and dir_data:
            rng = np.random.default_rng(0)
            strip_x = 0
            strip_ticks = []
            strip_lbls  = []
            for epoch_label, colors in [("pre", pre_colors), ("post", post_colors)]:
                for di, skey in enumerate(state_keys):
                    key  = (epoch_label, skey)
                    data = dir_data.get(key, {"wc_vals": []})
                    wc_v = np.asarray(data["wc_vals"])
                    col  = colors[di % len(colors)]
                    if len(wc_v) > 0:
                        jit = rng.uniform(-0.15, 0.15, len(wc_v))
                        ax_wc.scatter(np.full(len(wc_v), strip_x) + jit, wc_v,
                                      s=16, alpha=0.45, color=col, linewidths=0)
                        ax_wc.hlines(float(np.nanmean(wc_v)),
                                     strip_x - 0.25, strip_x + 0.25,
                                     colors="k", linewidths=2)
                    strip_ticks.append(strip_x)
                    short = skey.split("_")[-1]
                    strip_lbls.append(
                        f"{'Pre' if epoch_label == 'pre' else 'Post'}\n{short}")
                    strip_x += 1
                strip_x += 1   # gap between PRE and POST groups

            ax_wc.axhline(0, color="gray", linestyle=":", linewidth=1)
            ax_wc.set_xticks(strip_ticks)
            ax_wc.set_xticklabels(strip_lbls, fontsize=9)
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
