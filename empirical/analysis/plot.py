"""Plots for the empirical branch.

queries.png   x: security parameter lam (bits of the group order N), y: oracle queries (log2).
              - lower bound on the expected number of queries of any always-successful generic
                attack, averaged over a random lam-bit prime N (ggm.instances.lb_expected);
              - Sonnet's attacks: queries used on each fresh replay instance (+ median).
runtime.png   same x; y: wall-clock seconds of `python attack.py` on each replay (log scale).
runtime_extrapolated.png   runtime fit t = t0 + k*sqrt(N), extrapolated to lam = 256
              (analysis/runtime_fit.py); fit parameters in runtime_fit.json.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics as st
import sys

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ggm.instances import lb_expected  # noqa: E402

AGENT, LB = "#eb6834", "#2a78d6"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"


def lb_curve(lam: float, samples: int = 64) -> float:
    """E_N[lb_expected(N)] for N uniform on [2^(lam-1), 2^lam) (primes are near-uniform there)."""
    lo, hi = 2 ** (lam - 1), 2 ** lam
    vals = [float(lb_expected(int(lo + (hi - lo) * (k + 0.5) / samples))) for k in range(samples)]
    return sum(vals) / samples


def load(runs: str) -> list[dict]:
    pts = []
    for d in sorted(os.listdir(runs)):
        p = os.path.join(runs, d, "result.json")
        if not os.path.exists(p):
            continue
        rec = json.load(open(p, encoding="utf-8"))
        for r in rec.get("replays") or []:
            pts.append({**r, "episode": rec["episode"]})
    return pts


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _median_line(ax, pts, key, transform):
    lams = sorted({p["lam"] for p in pts})
    xs, ys = [], []
    for L in lams:
        v = [transform(p[key]) for p in pts if p["lam"] == L]
        if v:
            xs.append(L)
            ys.append(st.median(v))
    ax.plot(xs, ys, color=AGENT, linewidth=2, zorder=2)


def plot_queries(pts, out, label):
    ok = [p for p in pts if p["solved"]]
    fail = [p for p in pts if not p["solved"]]
    lams = sorted({p["lam"] for p in pts}) or [16, 40]
    lo, hi = min(lams) - 1, max(lams) + 1
    grid = [lo + (hi - lo) * k / 60 for k in range(61)]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    _style(ax)
    ax.plot(grid, [math.log2(lb_curve(x)) for x in grid], color=LB, linewidth=2,
            label="lower bound on expected queries (generic, ≈0.81·2^(λ/2))")
    ax.scatter([p["lam"] for p in ok], [math.log2(p["queries_at_solve"]) for p in ok], s=40, color=AGENT,
               marker="s", edgecolor="white", linewidth=1.5, zorder=3, label=f"{label} (fresh instances)")
    if ok:
        _median_line(ax, ok, "queries_at_solve", math.log2)
    if fail:
        ax.scatter([p["lam"] for p in fail], [math.log2(max(1, p["queries_used"])) for p in fail], s=40,
                   facecolor="none", edgecolor=AGENT, marker="X", linewidth=1.5, zorder=3,
                   label=f"{label}: failed run (queries used)")
    ax.set_xlabel("security parameter λ = log2 N  (bits)", fontsize=10, color=MUTED)
    ax.set_ylabel("oracle queries  (log2)", fontsize=10, color=MUTED)
    ax.set_title("Generic discrete log: queries vs security parameter", fontsize=11, color=INK, loc="left")
    ax.legend(fontsize=8.5, frameon=False, loc="upper left")
    ax.set_xlim(lo, hi)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def plot_runtime(pts, out, label):
    ok = [p for p in pts if p["solved"]]
    fail = [p for p in pts if not p["solved"]]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    _style(ax)
    ax.scatter([p["lam"] for p in ok], [p["wall_secs"] for p in ok], s=40, color=AGENT, marker="s",
               edgecolor="white", linewidth=1.5, zorder=3, label=f"{label} (fresh instances)")
    if ok:
        _median_line(ax, ok, "wall_secs", lambda v: v)
    if fail:
        ax.scatter([p["lam"] for p in fail], [p["wall_secs"] for p in fail], s=40, facecolor="none",
                   edgecolor=AGENT, marker="X", linewidth=1.5, zorder=3, label=f"{label}: failed run")
    ax.set_yscale("log")
    secs = [p["wall_secs"] for p in pts] or [1]
    ticks = [t for t in (0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300, 600, 1200, 1800, 3600)
             if min(secs) / 1.5 <= t <= max(secs) * 1.5]

    def fmt(t, _pos=None):
        if t < 60:
            return f"{t:g} s"
        return f"{t / 60:g} min" if t < 3600 else f"{t / 3600:g} h"

    ax.set_yticks(ticks)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(fmt))
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_xlabel("security parameter λ = log2 N  (bits)", fontsize=10, color=MUTED)
    ax.set_ylabel("wall-clock time per attack run  (log scale)", fontsize=10, color=MUTED)
    ax.set_title("Generic discrete log: attack runtime vs security parameter", fontsize=11, color=INK,
                 loc="left")
    ax.legend(fontsize=8.5, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="results/runs")
    ap.add_argument("--out", default="results")
    ap.add_argument("--label", default="Sonnet 5 (medium) attack")
    a = ap.parse_args()
    pts = load(a.runs)
    plot_queries(pts, os.path.join(a.out, "queries.png"), a.label)
    plot_runtime(pts, os.path.join(a.out, "runtime.png"), a.label)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import runtime_fit
    f = runtime_fit.plot_extrapolated([p for p in pts if p["solved"]],
                                      os.path.join(a.out, "runtime_extrapolated.png"), a.label)
    json.dump(f, open(os.path.join(a.out, "runtime_fit.json"), "w"), indent=1)
    rows = ["| λ | N (bits) | solved | queries | LB on E[queries] (this N) | queries / LB | wall-clock (s) |",
            "|---|---|---|---|---|---|---|"]
    for p in sorted(pts, key=lambda p: (p["lam"], p["episode"])):
        q = p["queries_at_solve"] if p["solved"] else p["queries_used"]
        rows.append(f"| {p['lam']} | {int(p['N']).bit_length()} | {p['solved']} | {q} | {p['lb_expected']:.0f} | "
                    f"{q / p['lb_expected']:.2f} | {p['wall_secs']:.1f} |")
    md = "\n".join(rows)
    open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8").write(md + "\n")
    sys.stdout.reconfigure(encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
