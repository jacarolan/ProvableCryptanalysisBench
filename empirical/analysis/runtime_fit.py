"""Extrapolate measured attack wall-clock time to large security parameters.

Model: t(N) = t0 + k * sqrt(N).
  t0  fixed per-run overhead (Python start-up, HTTP connection), estimated as the median time of
      the smallest-lam runs, where the sqrt(N) term is negligible;
  k   seconds per sqrt(N), the geometric mean of (t - t0)/sqrt(N) over runs with lam >= 28, where
      the overhead is a small fraction of the total.
Every measured attack is baby-step giant-step with ~1.5-2 sqrt(N) queries, so t grows like sqrt(N).
The extrapolation assumes the same machine, the same oracle and unlimited memory. BSGS also needs
~sqrt(N) stored labels, so beyond lam ~ 60-70 the time estimate is optimistic.
"""
from __future__ import annotations

import json
import math
import os
import statistics as st


def load_replays(runs_dir: str) -> list[dict]:
    pts = []
    for d in sorted(os.listdir(runs_dir)):
        p = os.path.join(runs_dir, d, "result.json")
        if os.path.exists(p):
            rec = json.load(open(p, encoding="utf-8"))
            pts += [{**r, "episode": rec["episode"]} for r in rec.get("replays") or [] if r["solved"]]
    return pts


def fit(pts: list[dict], min_lam_slope: int = 28) -> dict:
    lams = sorted({p["lam"] for p in pts})
    t0 = st.median(p["wall_secs"] for p in pts if p["lam"] == lams[0])
    big = [p for p in pts if p["lam"] >= min_lam_slope and p["wall_secs"] > t0]
    logk = [math.log(p["wall_secs"] - t0) - 0.5 * math.log(int(p["N"])) for p in big]
    k = math.exp(sum(logk) / len(logk))
    qs = [p["queries_at_solve"] / math.sqrt(int(p["N"])) for p in big]
    return {"t0_secs": t0, "k_secs_per_sqrtN": k, "n_points_slope": len(big), "min_lam_slope": min_lam_slope,
            "secs_per_query": k / st.median(qs), "model": "t = t0 + k*sqrt(N)"}


def log10_predict(f: dict, lam: float) -> float:
    """log10 of predicted seconds at a lam-bit N (N ~ 2^(lam - 0.5), the geometric middle of the range)."""
    log10_sqrtN = (lam - 0.5) / 2 * math.log10(2)
    big = math.log10(f["k_secs_per_sqrtN"]) + log10_sqrtN
    if big > 15:  # t0 negligible; avoid float overflow
        return big
    return math.log10(f["t0_secs"] + 10 ** big)


YEAR = 365.25 * 24 * 3600
AGE_OF_UNIVERSE_SECS = 13.8e9 * YEAR


def fmt_log10_secs(v: float) -> str:
    """Human label for 10^v seconds."""
    t = 10 ** v * (1 + 1e-9) if v < 300 else None  # tolerance so exact unit boundaries round up
    if t is not None and t < 60:
        return f"{t:g} s"
    if t is not None and t < 3600:
        return f"{t / 60:g} min"
    if t is not None and t < 86400:
        return f"{t / 3600:g} h"
    if t is not None and t < YEAR:
        d = round(t / 86400, 6)
        return "1 day" if d == 1 else f"{d:g} days"
    yrs = v - math.log10(YEAR)
    if yrs < 4:
        y = round(10 ** yrs, 6)
        return "1 year" if y == 1 else f"{y:g} years"
    return f"$10^{{{yrs:.0f}}}$ years"


def plot_extrapolated(pts: list[dict], out: str, label: str = "Sonnet 5 (medium) attack",
                      lam_max: int = 256) -> dict:
    """Measured runtimes (lam <= 40) and the fitted t0 + k*sqrt(N) curve extrapolated to lam_max.
    x: lam on a LINEAR axis; y: seconds on a log axis (human-readable labels). With N ~ 2^lam,
    log t = log k + (lam/2) log 2 once t0 is negligible: a straight line of slope 1/2 bit per bit."""
    import matplotlib
    import matplotlib.ticker
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    f = fit(pts)
    lam_meas = max(p["lam"] for p in pts)
    grid = [16 + (lam_max - 16) * i / 400 for i in range(401)]
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    for s_ in ("left", "bottom"):
        ax.spines[s_].set_color("#52514e")
    ax.tick_params(colors="#52514e", labelsize=9)
    ax.grid(True, color="#e6e5e0", linewidth=0.8)
    ax.set_axisbelow(True)
    inside = [L for L in grid if L <= lam_meas]
    beyond = [L for L in grid if L >= lam_meas]
    ax.plot(inside, [log10_predict(f, L) for L in inside], color="#eb6834", linewidth=2,
            label=f"fit  t = {f['t0_secs']:.2f} s + {f['k_secs_per_sqrtN'] * 1e3:.2f} ms·√N")
    ax.plot(beyond, [log10_predict(f, L) for L in beyond], color="#eb6834", linewidth=2, linestyle="--",
            label="extrapolation (same machine, unlimited memory)")
    ax.scatter([p["lam"] for p in pts], [math.log10(p["wall_secs"]) for p in pts], s=26, color="#eb6834",
               marker="s", edgecolor="white", linewidth=1, zorder=4, label=f"{label}: measured runs")
    top = log10_predict(f, lam_max)
    for v, name in ((math.log10(86400), "1 day"), (math.log10(YEAR), "1 year"),
                    (math.log10(AGE_OF_UNIVERSE_SECS), "age of the universe")):
        ax.axhline(v, color="#8a8984", linewidth=0.9, linestyle=":")
        ax.text(lam_max, v, name + " ", color="#52514e", fontsize=7.5, va="bottom", ha="right")
    ax.set_xticks([16] + list(range(32, lam_max + 1, 32)))
    ax.set_xlim(12, lam_max + 4)
    y_year = math.log10(YEAR)
    yt = [0, math.log10(60), math.log10(3600), math.log10(86400), y_year]
    yt += [y_year + k for k in range(5, int(top - y_year) + 5, 5)]
    ax.set_yticks([y for y in yt if y <= top + 2])
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: fmt_log10_secs(v)))
    ax.set_ylim(math.log10(0.3), top + 1.5)
    ax.set_xlabel("security parameter λ = log2 N  (bits)", fontsize=10, color="#52514e")
    ax.set_ylabel("wall-clock time per attack run  (log scale)", fontsize=10, color="#52514e")
    ax.set_title(f"Empirical attack runtime: measured to λ = {lam_meas}, extrapolated to λ = {lam_max}",
                 fontsize=11, color="#0b0b0b", loc="left")
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return f
