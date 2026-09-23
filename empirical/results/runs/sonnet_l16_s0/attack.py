"""Baby-step Giant-step attack on a generic-group discrete-log challenger.

The oracle exposes a cyclic group G of prime order N with generator g and
h = g^x. Group elements are only visible as opaque labels; we can only
combine them via the oracle's mul/inv/exp ops (each costs one query).

Standard BSGS:
  m = ceil(sqrt(N))
  baby steps:  g^0, g^1, ..., g^(m-1)          -> table label -> j
  giant steps: h, h*g^-m, h*g^-2m, ...         -> for i = 0..m-1
  if h*g^-(i*m) == g^j  then  x = j + i*m  (mod N)

Each baby/giant step is built by chaining a single multiplication onto the
previous result within one oracle batch (using "$k" back-references), so the
whole baby-step table costs exactly m queries and the whole giant-step walk
costs m+1 queries (one extra to compute g^-m) -- all within a couple of HTTP
round trips. Total queries ~= 2*sqrt(N) + O(1), far under the 1988 budget for
16-bit N (sqrt(N) <= ~256).
"""
from __future__ import annotations

import math
import sys

from oracle_client import Oracle, OracleError


def bsgs(o: Oracle, N: int, g: str, h: str) -> int:
    m = math.isqrt(N) + 1  # ceil-ish; safe since m*m >= N

    # --- baby steps: g^0 .. g^(m-1), chained via multiplication ---
    baby_ops = [["exp", g, 0]]
    for _ in range(m - 1):
        baby_ops.append(["mul", "$" + str(len(baby_ops) - 1), g])
    baby_results = o.query(baby_ops)

    table = {}
    for j, lab in enumerate(baby_results):
        table.setdefault(lab, j)

    # quick check: maybe h is already in the baby table (x < m)
    if h in table:
        return table[h]

    # --- giant steps: h * (g^-m)^i for i = 1..m-1, chained via multiplication ---
    giant_ops = [["exp", g, -m]]  # $0 = g^-m
    for i in range(1, m):
        if i == 1:
            giant_ops.append(["mul", h, "$0"])
        else:
            giant_ops.append(["mul", "$" + str(len(giant_ops) - 1), "$0"])
    giant_results = o.query(giant_ops)

    # giant_results[0] is g^-m itself; the actual giant steps start at index 1
    for i in range(1, m):
        lab = giant_results[i]
        if lab in table:
            j = table[lab]
            x = (j + i * m) % N
            return x

    raise RuntimeError("BSGS failed to find a match (unexpected)")


def main():
    o = Oracle()
    N = int(o.instance["N"])
    labels = o.instance["labels"]
    g, h = labels["g"], labels["h"]

    x = bsgs(o, N, g, h)

    ok = o.submit(x)
    print(f"N={N} x={x} correct={ok} queries_used={o.queries_used} budget={o.budget}")
    if not ok:
        print("submission was rejected", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
