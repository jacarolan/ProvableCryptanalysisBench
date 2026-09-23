"""Baby-step giant-step attack on a generic-group DLOG challenger.

The challenger's key generation samples x uniformly from [0, 2^t) for a
(small) parameter t published as part of the instance. Because the search
space for x is only 2^t, a classic baby-step / giant-step (BSGS) algorithm
recovers x using about 2*sqrt(2^t) group-operation queries plus a handful
of setup queries -- far below any reasonable budget even for the live
instance's budget of 1024 queries (t=14 => ~257 queries total).

Group elements are only ever compared by label equality (which is exactly
equivalent to element equality, since the labeling is an injection), so no
arithmetic is ever performed locally on labels -- every mul/inv/exp is done
by the oracle, and we simply compare the returned opaque label strings.

Algorithm:
  1. Read N, t, g, h from GET /instance.
  2. m = ceil(sqrt(2**t))   (smallest m with m*m >= 2**t)
  3. Baby steps: bs[i] = g^i for i = 0..m-1        (m queries, batched)
  4. Giant step base: gm = (g^-1)^m                 (2 queries: inv, exp)
  5. Giant steps: gs[j] = h * gm^j for j = 0..m-1
     computed incrementally: gs[0] = h (free), gs[j] = gs[j-1] * gm
     (m-1 queries, batched)
  6. Whenever bs[i] == gs[j] (label equality), we have
        g^i == h * g^(-jm)  =>  h == g^(i + j*m)  =>  x = i + j*m (mod N)
  7. Submit x.

Total oracle queries: m (baby steps) + 1 (inv) + 1 (exp) + (m-1) (giant
steps) + 1 (submit) = 2*m + 2 queries. For t=14, m=128 => 258 queries.
"""
from __future__ import annotations

import math
import sys

from oracle_client import Oracle, OracleError


def ceil_sqrt_pow2(t: int) -> int:
    """Smallest m such that m*m >= 2**t."""
    n = 1 << t
    m = math.isqrt(n)
    if m * m < n:
        m += 1
    return m


def bsgs(o: Oracle) -> int:
    inst = o.instance
    N = int(inst["N"])
    params = inst.get("params") or {}
    if "t" in params:
        t = int(params["t"])
    elif "t" in inst:
        t = int(inst["t"])
    else:
        raise RuntimeError("could not find parameter t in instance data")
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]

    m = ceil_sqrt_pow2(t)

    # Baby steps: g^0 .. g^(m-1), batched into as few round trips as the
    # per-request op cap allows (200000 ops/request, so one batch suffices
    # for any realistic t).
    baby_ops = [["exp", g, i] for i in range(m)]
    baby_labels = o.query(baby_ops)
    baby_index = {}
    for i, lab in enumerate(baby_labels):
        baby_index.setdefault(lab, i)  # keep smallest i on collision (shouldn't happen)

    # Giant step base: gm = (g^-1)^m
    ginv = o.inv(g)
    gm = o.exp(ginv, m)

    # Giant steps: gs_0 = h, gs_j = gs_{j-1} * gm, checking against baby steps.
    if h in baby_index:
        x = baby_index[h]
        return x % N

    # Build the whole chain of multiplications gs_1 = h*gm, gs_2 = gs_1*gm, ...
    # in a single batch, using "$i" to refer to this batch's own i-th result.
    ops = []
    for j in range(1, m):
        prev_ref = h if j == 1 else f"${j - 2}"
        ops.append(["mul", prev_ref, gm])
    giant_labels = o.query(ops) if ops else []

    for j, lab in enumerate(giant_labels, start=1):
        if lab in baby_index:
            i = baby_index[lab]
            x = (i + j * m) % N
            return x

    raise RuntimeError("BSGS failed to find a match within [0, m^2)")


def main():
    o = Oracle()
    x = bsgs(o)
    ok = o.submit(x)
    print(f"x = {x}")
    print(f"submit correct: {ok}")
    print(f"queries used: {o.queries_used} / {o.budget}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
