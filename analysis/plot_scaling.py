"""Per-rung scaling plot: security parameter (bits) vs log2(queries).

For each rung, lambda is the bit-size of the unknown the generic lower bound is taken over:
  rung 1: log2 q_max                  (largest prime factor of N)
  rung 2: t                           (x < 2^t)
  rung 3: log2(2^t / S)               (residual interval after Pohlig-Hellman on the smooth part S)
  rung 4: log2((p-1)/d)               (order of the subgroup containing x^d)
Plotted: the agent's live instances (one point per episode), the reference attack on the 57
verification instances (line through per-level means, faint markers per instance), and the
generic lower bound Q*_LB(lambda) at success probability 1/2 (THEORY.md, Lemma 1).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics as st
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ggmbench import bounds  # noqa: E402
from ggmbench.instances import generate  # noqa: E402

AGENT, REF, LB = "#eb6834", "#52514e", "#2a78d6"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"
TITLES = {1: "Rung 1: smooth order", 2: "Rung 2: short exponent", 3: "Rung 3: smooth + short",
          4: "Rung 4: auxiliary g^(x^d)"}
XLABELS = {1: "λ = log2 q_max  (bits)", 2: "λ = t  (bits)", 3: "λ = log2(2^t / S)  (bits)",
           4: "λ = log2((p−1)/d)  (bits)"}


def lam(rung: int, structure: dict) -> float:
    if rung == 1:
        return math.log2(int(structure["q_max"]))
    if rung == 2:
        return float(structure["interval_bits"])
    if rung == 3:
        return math.log2(int(structure["residual_interval"]))
    return math.log2(int(structure["(p-1)/d"]))


def lower_bound(rung: int, lam_bits: float, d: int = 1 << 14) -> float:
    """log2 Q*_LB as a function of lambda (rung 4 uses a representative 14-bit d)."""
    M = 2 ** lam_bits
    if rung == 4:
        return math.log2(max(1, bounds.lb_queries(int(M * d), k0=3, delta=d)))
    return math.log2(max(1, bounds.lb_queries(int(M))))


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="results/subagent_runs")
    ap.add_argument("--reference", default="results/reference_verification.json")
    ap.add_argument("--out", default="results/subagent_pilot/scaling.png")
    ap.add_argument("--label", default="Sonnet 5 (live instance)")
    a = ap.parse_args()

    agent = {r: [] for r in (1, 2, 3, 4)}
    for d in sorted(os.listdir(a.runs)):
        p = os.path.join(a.runs, d, "result.json")
        if not os.path.exists(p):
            continue
        rec = json.load(open(p, encoding="utf-8"))
        live = rec.get("live", {})
        if rec.get("status") == "cancelled" or not live.get("solved"):
            continue
        agent[rec["rung"]].append((lam(rec["rung"], live["secret_structure"]),
                                   math.log2(live["queries_at_solve"])))

    ref = {r: [] for r in (1, 2, 3, 4)}
    for row in json.load(open(a.reference)):
        inst = generate(row["rung"], row["level"], 1000 + row["seed"])  # same seeds as verify_reference.py
        assert inst.q_ub == row["q_ub"]
        ref[row["rung"]].append((row["level"], lam(row["rung"], inst.secret_structure), math.log2(row["q_used"])))

    fig, axes = plt.subplots(1, 4, figsize=(13, 3.6))
    for i, rung in enumerate((1, 2, 3, 4)):
        ax = axes[i]
        _style(ax)
        pts = ref[rung]
        levels = sorted({p[0] for p in pts})
        mx = [st.mean(p[1] for p in pts if p[0] == L) for L in levels]
        my = [st.mean(p[2] for p in pts if p[0] == L) for L in levels]
        ax.scatter([p[1] for p in pts], [p[2] for p in pts], s=10, color=REF, alpha=0.35, linewidth=0)
        ax.plot(mx, my, color=REF, linewidth=1.5, linestyle="--", marker="D", markersize=4,
                label="reference attack")
        xs_all = [p[1] for p in pts] + [p[0] for p in agent[rung]]
        lo, hi = min(xs_all) - 0.5, max(xs_all) + 0.5
        grid = [lo + (hi - lo) * k / 100 for k in range(101)]
        ax.plot(grid, [lower_bound(rung, x) for x in grid], color=LB, linewidth=2,
                label="generic lower bound (success ½)")
        if agent[rung]:
            ax.scatter([p[0] for p in agent[rung]], [p[1] for p in agent[rung]], s=46, color=AGENT,
                       marker="s", edgecolor="white", linewidth=1.5, zorder=3, label=a.label)
        ax.set_title(TITLES[rung], fontsize=9, color=INK, loc="left")
        ax.set_xlabel(XLABELS[rung], fontsize=8, color=MUTED)
        ax.set_xlim(lo, hi)
    axes[0].set_ylabel("log2(oracle queries)", fontsize=8, color=MUTED)
    handles, labels = [], []
    for ax in axes:
        for h, l in zip(*ax.get_legend_handles_labels()):
            if l not in labels:
                handles.append(h)
                labels.append(l)
    fig.legend(handles, labels, loc="upper right", fontsize=8, frameon=False, ncol=len(labels))
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    fig.savefig(a.out, dpi=200)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
