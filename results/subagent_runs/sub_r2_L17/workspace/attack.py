"""Baby-step giant-step attack against a generic-group DL oracle where the
secret exponent x is known to lie in [0, 2^t) for some small t (here t=32,
vs. a group order N of ~127 bits). This bound makes a full sqrt(N) attack
unnecessary: BSGS only needs O(2^(t/2)) group operations (queries).

Given g, h = g^x with 0 <= x < 2^t:
  - baby steps:  B[j] = g^j                      for j = 0 .. m-1
  - giant steps: G[i] = h * g^(-m*i)             for i = 0 .. m-1
where m = ceil(sqrt(2^t)). If x = j + m*i (which covers the whole range
since m*m >= 2^t), then g^j == h * g^(-m*i), i.e. B[j] and G[i] are the
same group element and therefore have the same (opaque) label.

Total oracle cost: m queries for baby steps + m queries for giant steps
(chained via "$k" references in one batch each) + 1 submit query
= 2*ceil(sqrt(2^t)) + 1. For t=32, m=65536, so ~131073 queries -- well
under the 524288 budget.
"""
from __future__ import annotations

import math

from oracle_client import Oracle, OracleError


def ceil_isqrt(n: int) -> int:
    r = math.isqrt(n)
    if r * r < n:
        r += 1
    return r


def bsgs(o: Oracle, N: int, g: str, h: str, t: int) -> int:
    bound = 1 << t  # x in [0, bound)
    m = ceil_isqrt(bound)
    while m * m < bound:
        m += 1

    # --- baby steps: g^j for j = 0 .. m-1, batched with "$" chaining ---
    baby_map: dict[str, int] = {}
    CHUNK = 100_000  # keep well under the 200000-ops-per-batch limit
    j = 0
    while j < m:
        n = min(CHUNK, m - j)
        ops = [["exp", g, j + k] for k in range(n)]
        labels = o.query(ops)
        for k, lab in enumerate(labels):
            baby_map.setdefault(lab, j + k)
        j += n

    # --- giant steps: h * g^(-m*i) for i = 0 .. m-1 ---
    # ops[0] = g^(-m); ops[k] (k=1..) = $(k-1 or h) * g^(-m) => i=k
    gm_inv = o.query([["exp", g, -m]])[0]

    def check(label: str, i: int):
        if label in baby_map:
            j = baby_map[label]
            x = j + m * i
            if 0 <= x < bound:
                return x
        return None

    x_found = check(h, 0)
    if x_found is not None:
        return x_found

    i = 1
    prev_label = h
    while i < m:
        n = min(CHUNK, m - i)
        ops = []
        for k in range(n):
            if k == 0:
                ops.append(["mul", prev_label, gm_inv])
            else:
                ops.append(["mul", f"${k - 1}", gm_inv])
        labels = o.query(ops)
        for k, lab in enumerate(labels):
            res = check(lab, i + k)
            if res is not None:
                return res
        prev_label = labels[-1]
        i += n

    raise RuntimeError("BSGS failed to find x within the claimed bound")


def main():
    o = Oracle()
    inst = o.instance
    N = int(inst["N"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]
    params = inst.get("params", {}) or {}
    t = int(params.get("t", 32))

    x = bsgs(o, N, g, h, t)

    # sanity check before spending the submit query, if budget allows
    try:
        check_label = o.exp(g, x)
        if check_label != h:
            raise RuntimeError(f"verification failed: g^{x} != h")
    except OracleError:
        pass

    ok = o.submit(x)
    print(f"x = {x}")
    print(f"submit correct = {ok}")
    print(f"queries_used = {o.queries_used} / budget = {o.budget}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
