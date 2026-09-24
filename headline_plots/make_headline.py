"""Headline figures combining the empirical and provable branches.

    py -3.13 headline_plots/make_headline.py

Writes into headline_plots/:
  queries.png                 expected oracle queries (log scale) vs security parameter lam = log2 N
                              (linear, 16..256): generic lower bound (line), empirical measured runs
                              (dots, lam <= 40), provable certified bound (curve). sqrt(N) scaling is
                              a straight line of slope 1/2 on these axes.
  runtime_extrapolated.png    empirical attack wall-clock, measured to lam = 40, fitted
                              t = t0 + k*sqrt(N) and extrapolated to lam = 256.
  provable_runtimes.md        per proof: bound, agent session time, proof-check time (valid for all N).
Inputs are read from ../empirical/results and ../provable/results; nothing there is modified.
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import statistics as st

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
EMP, PRV = REPO / "empirical", REPO / "provable"
LB_C, EMP_C, PRV_C = "#1baf7a", "#eb6834", "#2a78d6"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


runtime_fit = load_module("emp_runtime_fit", EMP / "analysis" / "runtime_fit.py")
evaluate = load_module("prv_evaluate", PRV / "run" / "evaluate.py")


LAM_MAX = 256


def style(ax):
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    for s_ in ("left", "bottom"):
        ax.spines[s_].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xticks([16] + list(range(32, LAM_MAX + 1, 32)))
    ax.set_xlim(12, LAM_MAX + 4)
    ax.set_xlabel("security parameter λ = log2 N  (bits)", fontsize=10, color=MUTED)


def by_lam(rows, key):
    out = {}
    for r in rows:
        if r.get(key) is not None:
            out.setdefault(r["lam"], []).append(r[key])
    lams = sorted(out)
    return lams, [st.median(out[L]) for L in lams]


def human(t: float) -> str:
    return f"{t:.0f} s" if t < 90 else (f"{t / 60:.1f} min" if t < 5400 else f"{t / 3600:.1f} h")


def load_proofs() -> list[dict]:
    recs = []
    for d in sorted((PRV / "results" / "runs").iterdir()):
        p = d / "result.json"
        if p.is_file():
            rec = json.loads(p.read_text(encoding="utf-8"))
            if rec.get("status") == "accepted" and "reference" not in rec.get("model", ""):
                recs.append(rec)
    return recs


def plot_queries(emp_pts, proofs, out):
    """y = log2(queries) on a linear scale (labelled 2^k), x = lam linear: sqrt(N) is a line."""
    lams = sorted({r["lam"] for rec in proofs for r in rec["evaluation"] if r["lam"] <= LAM_MAX})
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    style(ax)
    xl, yl = by_lam(evaluate.evaluate_lams({"op": "constant", "value": 1}, lams), "log2_lb_expected")
    ax.plot(xl, yl, color=LB_C, linewidth=2.5, zorder=2,
            label="generic lower bound on expected queries (≈0.94·√N, proven)")
    for i, rec in enumerate(proofs):
        xs, ys = by_lam([r for r in rec["evaluation"] if r["lam"] <= LAM_MAX], "log2_certified")
        ax.plot(xs, ys, color=PRV_C, linewidth=1.8, alpha=0.85, zorder=3,
                label=f"provable: Sonnet 5 certified bound (Lean, {len(proofs)} proofs)" if i == 0 else None)
    ax.scatter([p["lam"] for p in emp_pts], [math.log2(p["queries_at_solve"]) for p in emp_pts], s=24,
               color=EMP_C, marker="s", edgecolor="white", linewidth=0.8, zorder=4,
               label="empirical: Sonnet 5 attack, measured runs (λ ≤ 40)")
    ax.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(16))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"$2^{{{v:g}}}$"))
    ax.set_ylabel("expected oracle queries  (log scale)", fontsize=10, color=MUTED)
    ax.set_title("Generic discrete log: queries vs security parameter", fontsize=11, color=INK, loc="left")
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def runtimes_table(proofs) -> str:
    lines = [
        "# Provable branch: runtimes (Sonnet 5, medium effort, Claude Code subagent)",
        "",
        "Each row is **one Lean proof that holds for every prime group order N**, i.e. for every",
        "security parameter λ at once. Its cost is paid once and does not grow with λ, unlike the",
        "empirical attack runtime (see `runtime_extrapolated.png`).",
        "",
        "| proof | certified expected queries (all prime N) | agent session (wall-clock) | independent proof check |",
        "|---|---|---|---|",
    ]
    for rec in proofs:
        b = rec["certificate"]["bound"]
        try:
            const = b["b"]["value"]
            expr = f"2·⌊√N⌋ + {const}" if b["a"]["a"]["value"] == 2 and b["a"]["b"]["op"] == "sqrtOrder" else json.dumps(b)
        except (KeyError, TypeError):
            expr = json.dumps(b)
        lines.append(f"| {rec['episode']} | {expr} | {human(rec['agent_wall_secs'])} | "
                     f"{human(rec['verification_wall_secs'])} |")
    s = [r["agent_wall_secs"] for r in proofs]
    c = [r["verification_wall_secs"] for r in proofs]
    lines += [f"| **median** | | **{human(st.median(s))}** | **{human(st.median(c))}** |", "",
              "- Agent session: first to last event of the subagent transcript (writing the attack and the",
              "  proof, including its own checker runs).",
              "- Proof check: the host's independent fresh compilation with kernel checking and an axiom audit",
              "  (`propext`, `Classical.choice`, `Quot.sound` only); most of it is loading Mathlib.",
              "- Three earlier attempts were cut off by a plan rate limit before any check and are not included."]
    return "\n".join(lines) + "\n"


def main():
    emp_pts = runtime_fit.load_replays(str(EMP / "results" / "runs"))
    proofs = load_proofs()
    plot_queries(emp_pts, proofs, HERE / "queries.png")
    f = runtime_fit.plot_extrapolated(emp_pts, str(HERE / "runtime_extrapolated.png"),
                                      "Sonnet 5 (medium) attack")
    (HERE / "runtime_fit.json").write_text(json.dumps(f, indent=1), encoding="utf-8")
    (HERE / "provable_runtimes.md").write_text(runtimes_table(proofs), encoding="utf-8")
    print("wrote", *sorted(p.name for p in HERE.iterdir() if p.suffix in (".png", ".md", ".json")))


if __name__ == "__main__":
    main()
