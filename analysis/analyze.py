"""Aggregate episodes -> summary table + the two headline plots.

Primary outcome per episode = the submitted attack.py replayed on fresh instances (same rung and
level, budget 4 Q*_UB). Q_model = median queries-at-solve over successful replays.
Efficiency = log2(Q_model / Q*_UB); the certified band is [log2(Q*_LB/Q*_UB), 0] and the
budget sits at +2.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics as st

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

COLORS = {"claude-opus-5-5": "#2a78d6", "claude-sonnet-5": "#eb6834", "claude-sonnet-5 (subagent)": "#eb6834",
          "reference": "#52514e"}
NAMES = {"claude-opus-5-5": "Opus 5.5", "claude-sonnet-5": "Sonnet 5",
         "claude-sonnet-5 (subagent)": "Sonnet 5 (subagent)", "reference": "reference attack"}
MARKERS = {"claude-opus-5-5": "o", "claude-sonnet-5": "s", "claude-sonnet-5 (subagent)": "s", "reference": "D"}
RUNG_TITLES = {1: "Rung 1: smooth order", 2: "Rung 2: short exponent", 3: "Rung 3: smooth + short",
               4: "Rung 4: auxiliary g^(x^d)"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"


def load(runs: str) -> list[dict]:
    out = []
    for d in sorted(os.listdir(runs)):
        p = os.path.join(runs, d, "result.json")
        if os.path.exists(p):
            out.append(json.load(open(p, encoding="utf-8")))
    return out


def summarize(rec: dict) -> dict:
    live = rec.get("live", {})
    reps = rec.get("replays") or []
    ok = [r for r in reps if r["solved"]]
    q_ub = live.get("q_ub") or (reps[0]["q_ub"] if reps else None)
    q_lb = live.get("q_lb") or (reps[0]["q_lb"] if reps else None)
    # replays are fresh instances with their own Q*; normalise per replay
    eff = [math.log2(r["queries_at_solve"] / r["q_ub"]) for r in ok]
    return {
        "episode": rec["episode"], "model": rec["model"], "rung": rec["rung"], "level": rec["level"],
        "rep": rec["rep"], "status": rec["status"], "refused": rec["status"] == "refused",
        "live_solved": bool(live.get("solved")), "live_queries_at_solve": live.get("queries_at_solve"),
        "live_queries_used": live.get("queries_used"), "budget": live.get("budget"),
        "q_ub": q_ub, "q_lb": q_lb, "log2_q_ub": math.log2(q_ub) if q_ub else None,
        "replay_success": (len(ok) / len(reps)) if reps else 0.0, "n_replays": len(reps),
        "efficiency": st.median(eff) if eff else None,
        "live_efficiency": math.log2(live["queries_at_solve"] / q_ub) if live.get("solved") else None,
        "turns": rec.get("turns"), "wall_secs": rec.get("wall_secs"),
        "output_tokens": rec.get("usage", {}).get("output_tokens"),
        "input_tokens": sum(rec.get("usage", {}).get(k, 0) for k in
                            ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")),
    }


def reference_rows(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    rows = json.load(open(path))
    return [{"model": "reference", "rung": r["rung"], "level": r["level"], "log2_q_ub": math.log2(r["q_ub"]),
             "replay_success": 1.0 if r["solved"] else 0.0, "efficiency": math.log2(r["q_used"] / r["q_ub"]),
             "q_lb": r["q_lb"], "q_ub": r["q_ub"]} for r in rows]


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _groups(rows, key):
    g: dict = {}
    for r in rows:
        if r.get(key) is None:
            continue
        g.setdefault((r["model"], r["rung"], r["level"]), []).append(r)
    return g


def plot_success(rows, ref, out):
    fig, axes = plt.subplots(1, 4, figsize=(12, 3.1), sharey=True)
    models = [m for m in COLORS if m != "reference" and any(r["model"] == m for r in rows)]
    for i, rung in enumerate([1, 2, 3, 4]):
        ax = axes[i]
        _style(ax)
        for j, m in enumerate(models):
            pts = sorted(((st.mean(r["log2_q_ub"] for r in v), st.mean(r["replay_success"] for r in v), len(v))
                          for (mm, rr, L), v in _groups(rows, "log2_q_ub").items() if mm == m and rr == rung))
            if not pts:
                continue
            xs = [p[0] + (j - 0.5) * 0.25 for p in pts]
            ax.plot(xs, [p[1] for p in pts], color=COLORS[m], linewidth=2, marker=MARKERS[m], markersize=6,
                    markeredgecolor="white", markeredgewidth=1.5, label=NAMES[m])
        ax.set_title(RUNG_TITLES[rung], fontsize=9, color=INK, loc="left")
        ax.set_xlabel("certified optimal cost  log2 Q*", fontsize=8, color=MUTED)
        ax.set_ylim(-0.05, 1.05)
        ax.set_xlim(7, 21)
    axes[0].set_ylabel("attack success rate\n(fresh instances, budget 4Q*)", fontsize=8, color=MUTED)
    handles, labels = axes[0].get_legend_handles_labels()
    for a in axes[1:]:
        h, l = a.get_legend_handles_labels()
        for hh, ll in zip(h, l):
            if ll not in labels:
                handles.append(hh)
                labels.append(ll)
    fig.legend(handles, labels, loc="upper right", fontsize=8, frameon=False, ncol=len(labels))
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out, dpi=200)
    plt.close(fig)


def plot_efficiency(rows, ref, out):
    fig, axes = plt.subplots(1, 4, figsize=(12, 3.3), sharey=True)
    models = [m for m in COLORS if m != "reference" and any(r["model"] == m for r in rows)]
    for i, rung in enumerate([1, 2, 3, 4]):
        ax = axes[i]
        _style(ax)
        rr = [r for r in ref if r["rung"] == rung]
        if rr:
            lb = sorted({(r["level"], math.log2(r["q_lb"] / r["q_ub"])) for r in rr})
            ax.fill_between([7, 21], min(v for _, v in lb), 0, color="#d6d5cf", alpha=0.6, linewidth=0,
                            label="certified band [Q*_LB, Q*_UB]")
            g = _groups(rr, "efficiency")
            pts = sorted((st.mean(r["log2_q_ub"] for r in v), st.median(r["efficiency"] for r in v))
                         for v in g.values())
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color=COLORS["reference"], linestyle="--",
                    linewidth=1.5, marker="D", markersize=4, label=NAMES["reference"])
        ax.axhline(2, color="#e34948", linewidth=1, linestyle=":", label="budget (4Q*)")
        for j, m in enumerate(models):
            for r in rows:
                if r["model"] != m or r["rung"] != rung or r.get("efficiency") is None:
                    continue
                ax.scatter(r["log2_q_ub"] + (j - 0.5) * 0.25, r["efficiency"], s=36, color=COLORS[m],
                           marker=MARKERS[m], edgecolor="white", linewidth=1.5, zorder=3,
                           label=NAMES[m])
        ax.set_title(RUNG_TITLES[rung], fontsize=9, color=INK, loc="left")
        ax.set_xlabel("certified optimal cost  log2 Q*", fontsize=8, color=MUTED)
        ax.set_xlim(7, 21)
        ax.set_ylim(-1.6, 2.6)
    axes[0].set_ylabel("efficiency  log2(Q_model / Q*)\n(successful attacks)", fontsize=8, color=MUTED)
    seen, handles, labels = set(), [], []
    for a in axes:
        for h, l in zip(*a.get_legend_handles_labels()):
            if l not in seen:
                seen.add(l)
                handles.append(h)
                labels.append(l)
    fig.legend(handles, labels, loc="upper right", fontsize=8, frameon=False, ncol=len(labels))
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(out, dpi=200)
    plt.close(fig)


def table(rows) -> str:
    lines = ["| model | rung | level | seeds | log2 Q* | replay success | live solved | median eff. | refusals |",
             "|---|---|---|---|---|---|---|---|---|"]
    g: dict = {}
    for r in rows:
        g.setdefault((r["model"], r["rung"], r["level"]), []).append(r)
    for (m, rung, L), v in sorted(g.items()):
        effs = [r["efficiency"] for r in v if r["efficiency"] is not None]
        lq = [r["log2_q_ub"] for r in v if r["log2_q_ub"]]
        lines.append(f"| {NAMES.get(m, m)} | {rung} | {L} | {len(v)} | {st.mean(lq):.1f} | "
                     f"{st.mean(r['replay_success'] for r in v):.2f} | "
                     f"{sum(r['live_solved'] for r in v)}/{len(v)} | "
                     f"{(f'{st.median(effs):+.2f}') if effs else '-'} | {sum(r['refused'] for r in v)} |")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="results/runs")
    ap.add_argument("--reference", default="results/reference_verification.json")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows = [summarize(r) for r in load(a.runs)]
    ref = reference_rows(a.reference)
    json.dump(rows, open(os.path.join(a.out, "summary.json"), "w"), indent=1)
    plot_success(rows, ref, os.path.join(a.out, "success_vs_difficulty.png"))
    plot_efficiency(rows, ref, os.path.join(a.out, "efficiency.png"))
    md = table(rows)
    open(os.path.join(a.out, "summary.md"), "w").write(md + "\n")
    print(md)
