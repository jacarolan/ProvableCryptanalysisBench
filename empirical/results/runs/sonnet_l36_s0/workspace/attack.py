"""Baby-step giant-step attack on the generic-group DLP challenger.

The challenger's group G has known prime order N (given at /instance), with
generator g and h = g^x for unknown x in [0, N). We cannot compute on group
elements ourselves -- only the oracle can multiply / invert / exponentiate,
and equal outputs always get equal labels. This is exactly the generic group
model, so the best attacks are the sqrt(N)-time generic ones (BSGS, Pollard
rho/kangaroo). We use BSGS because it is deterministic, simple to batch, and
its query cost is a clean, provable ~2*sqrt(N).

BSGS:
  Pick m = ceil(sqrt(N)).
  Baby steps:  B[j] = g^j            for j = 0..m-1   (stored in a dict label->j)
  Giant steps: for i = 0..m-1: check whether h * g^(-m*i) is some B[j].
               If so x = i*m + j (mod N), since h = g^(i*m+j).
  Every g^j / g^(-m*i) is obtained by iterated multiplication (one oracle
  query per new element), and dictionary lookups are done locally on the
  opaque labels (label equality is free and exact).

Query cost: ~m queries to build the baby table, plus on average ~m/2 (worst
case m) queries for the giant steps, plus O(1) for computing g^-m and for the
final submission. For a 36-bit N, m ~ 2^18 (~2.6e5), so total queries are
roughly 3-8e5, comfortably inside the stated budget of 1,777,796 (and this
scales the same way for any fresh 36-bit-prime instance).

Batching: ops are sent in chunks (<= 200000 per request, we use much smaller
chunks so we can stop the giant-step search as soon as a match is found,
without wasting many post-match queries).
"""
from __future__ import annotations

import math
import sys
import time

from oracle_client import Oracle, OracleError

CHUNK = 20000  # ops per request; also the granularity at which we check for an early match


def build_chain(oracle: Oracle, start_label: str, step_label: str, count: int, op="mul"):
    """Return [start_label, start*step, start*step^2, ..., start*step^(count-1)]
    (labels only; the first element costs no query), doing `count-1` oracle
    multiplications in batches of CHUNK, using $-references inside each batch."""
    labels = [start_label]
    remaining = count - 1
    cur = start_label
    while remaining > 0:
        n = min(CHUNK, remaining)
        ops = []
        # first op in this batch multiplies the literal `cur` label
        ops.append([op, cur, step_label])
        for i in range(1, n):
            ops.append([op, f"${i - 1}", step_label])
        results = oracle.query(ops)
        labels.extend(results)
        cur = results[-1]
        remaining -= n
    return labels


def main():
    oracle = Oracle()
    inst = oracle.instance
    N = int(inst["N"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]

    t0 = time.time()

    m = math.isqrt(N)
    if m * m < N:
        m += 1
    m += 1  # small safety margin so m*m > N with room to spare

    # ---- Baby steps: B[j] = g^j for j = 0..m-1 ----
    g0 = oracle.exp(g, 0)  # identity element, 1 query
    baby = build_chain(oracle, g0, g, m, op="mul")
    baby_index = {lab: j for j, lab in enumerate(baby)}

    # ---- Giant steps: check h * g^(-m*i) for i = 0..m-1 ----
    g_inv_m = oracle.exp(g, -m)  # 1 query

    x = None
    cur = h
    i = 0
    # i = 0 case first (no query needed to obtain it)
    if cur in baby_index:
        x = baby_index[cur]
    else:
        while i < m - 1 and x is None:
            n = min(CHUNK, m - 1 - i)
            ops = [["mul", cur, g_inv_m]]
            for k in range(1, n):
                ops.append(["mul", f"${k - 1}", g_inv_m])
            results = oracle.query(ops)
            for k, lab in enumerate(results):
                if lab in baby_index:
                    j = baby_index[lab]
                    x = (i + k + 1) * m + j
                    break
            if x is not None:
                break
            cur = results[-1]
            i += n

    if x is None:
        print("FAILED to find x", file=sys.stderr)
        sys.exit(1)

    x %= N
    ok = oracle.submit(x)
    dt = time.time() - t0
    print(f"N={N} m={m} x={x} correct={ok} queries_used={oracle.queries_used} "
          f"budget={oracle.budget} time={dt:.1f}s")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
