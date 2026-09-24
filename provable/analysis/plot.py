"""Standalone plot for the provable branch.

queries.png   expected oracle queries (log scale) vs security parameter lam = log2 N (linear, 16..256):
                - generic lower bound on expected queries (lb_expected, shared with ../empirical);
                - Sonnet's certified expected-query bounds (kernel-checked, evaluated, never run);
                - the exhaustive-search reference certificate (bound N + 1).
              sqrt(N) scaling is a straight line (slope 1/2) on these axes.
summary.md    one row per episode: bound, values at lam = 128 and 256, session and check times.
Certificates are evaluated up to lam = 4096 (results/runs/*/result.json); plots stop at 256.
There is deliberately no runtime plot: one proof covers every lam, so its cost does not scale
with the security parameter (session and proof-check times are listed in summary.md).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics as st
import sys

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run.evaluate import DEFAULT_LAMS, evaluate_lams  # noqa: E402

PROOF, LB, REF = "#2a78d6", "#1baf7a", "#8a8984"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


LAM_MAX = 256


def lam_axis(ax):
    ax.set_xticks([16] + list(range(32, LAM_MAX + 1, 32)))
    ax.set_xlim(12, LAM_MAX + 4)
    ax.set_xlabel("security parameter λ = log2 N  (bits)", fontsize=10, color=MUTED)


def query_axis(ax):
    """y holds log2(queries) on a linear scale, labelled as powers of two: sqrt(N) scaling is a
    straight line of slope 1/2 against the linear lam axis."""
    ax.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(16))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"$2^{{{v:g}}}$"))
    ax.set_ylabel("expected oracle queries  (log scale)", fontsize=10, color=MUTED)


def by_lam(rows, key):
    out = {}
    for r in rows:
        if r.get(key) is not None:
            out.setdefault(r["lam"], []).append(r[key])
    lams = sorted(out)
    return lams, [st.median(out[L]) for L in lams]


def human(t: float) -> str:
    return f"{t:.0f} s" if t < 90 else (f"{t / 60:.1f} min" if t < 5400 else f"{t / 3600:.1f} h")


def load_proofs(runs: Path) -> list[dict]:
    recs = []
    for d in sorted(runs.iterdir()) if runs.is_dir() else []:
        p = d / "result.json"
        if p.is_file():
            rec = json.loads(p.read_text(encoding="utf-8"))
            if rec.get("status") == "accepted" and "reference" not in rec.get("model", ""):
                recs.append(rec)
    return recs


def plot_queries(proofs, ref_bound, lams, out):
    lams = [L for L in lams if L <= LAM_MAX]
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    style(ax)
    xl, yl = by_lam(evaluate_lams({"op": "constant", "value": 1}, lams), "log2_lb_expected")
    ax.plot(xl, yl, color=LB, linewidth=2.5, label="generic lower bound on E[queries] (≈0.94·√N)", zorder=4)
    if ref_bound is not None:
        xr, yr = by_lam(evaluate_lams(ref_bound, lams), "log2_certified")
        ax.plot(xr, yr, color=REF, linewidth=1.5, linestyle="--", label="exhaustive-search certificate (N + 1)")
    for i, rec in enumerate(proofs):
        rows = [r for r in rec["evaluation"] if r["lam"] <= LAM_MAX]
        xs, ys = by_lam(rows, "log2_certified")
        ax.plot(xs, ys, color=PROOF, linewidth=1.8, marker="o", markersize=3.5, alpha=0.8, zorder=3,
                label=f"Sonnet 5 (medium): certified bound, {len(proofs)} Lean proofs" if i == 0 else None)
    lam_axis(ax)
    query_axis(ax)
    ax.set_title("Certified expected queries vs security parameter", fontsize=11, color=INK, loc="left")
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def summary_table(runs: Path) -> str:
    rows = ["| episode | status | certified bound (Lean) | log2 bound / log2 LB at λ=128 | at λ=256 | "
            "session | proof check |", "|---|---|---|---|---|---|---|"]
    for d in sorted(runs.iterdir()) if runs.is_dir() else []:
        p = d / "result.json"
        if not p.is_file():
            continue
        rec = json.loads(p.read_text(encoding="utf-8"))
        ev = {r["lam"]: r for r in rec.get("evaluation") or [] if r["seed"] == 0}
        cell = lambda L: (f"{ev[L]['log2_certified']:.1f} / {ev[L]['log2_lb_expected']:.1f}" if L in ev else "-")
        sess, chk = rec.get("agent_wall_secs"), rec.get("verification_wall_secs")
        rows.append(f"| {rec['episode']} | {rec['status']} | {json.dumps((rec.get('certificate') or {}).get('bound'))} | "
                    f"{cell(128)} | {cell(256)} | {human(sess) if sess else '-'} | {human(chk) if chk else '-'} |")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=ROOT / "results" / "runs")
    ap.add_argument("--reference", type=Path, default=ROOT / "results" / "example-check.json")
    ap.add_argument("--out", type=Path, default=ROOT / "results")
    a = ap.parse_args()
    proofs = load_proofs(a.runs)
    lams = sorted({r["lam"] for rec in proofs for r in rec["evaluation"]}) or DEFAULT_LAMS
    ref = json.loads(a.reference.read_text())["certificate"]["bound"] if a.reference.is_file() else None
    plot_queries(proofs, ref, lams, a.out / "queries.png")
    md = summary_table(a.runs)
    (a.out / "summary.md").write_text(md + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
