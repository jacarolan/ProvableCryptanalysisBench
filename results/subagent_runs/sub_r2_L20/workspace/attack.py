"""Baby-step giant-step attack on a generic-group discrete-log challenger.

The challenger publishes a cyclic group of order N with generator g, and a
target h = g^x, together with the guarantee that the secret exponent x was
sampled uniformly from [0, 2^t). Group elements are shown to us only as
opaque, deterministic labels, and the only allowed operations are group
multiplication, inversion and exponentiation, each costing one oracle query.

Because x is *not* uniform over all of Z_N but is bounded by a much smaller
range [0, 2^t), the DL instance is far easier than a generic instance of the
full group order: baby-step giant-step (BSGS) over a search space of size
2^t costs only O(2^(t/2)) group operations/queries, rather than O(sqrt(N)).

Algorithm
---------
Let m = 2^ceil(t/2), so m^2 >= 2^t > x, i.e. x = i*m + j for some
0 <= i, j < m.

1. Baby steps: build a table {label(g^j): j} for j = 0..m-1, by chaining
   multiplications by g starting from g^0 (the identity). Labels are
   compared for equality directly (the challenger guarantees equal labels
   iff equal elements), so no extra queries are needed to compare.
2. Giant steps: compute gm = g^-m once, then walk h, h*gm, h*gm^2, ...
   (again via a multiplication chain) looking each one up in the baby
   table. If h*gm^i = g^j then h = g^(i*m+j), i.e. x = i*m + j.

Query cost: ~2*m + O(1) queries (m for the baby table, ~m for the giant
chain, plus a couple of exp() calls to seed the chains and one submit()).
For t=38, m = 2^19 = 524288, so total cost is ~1,048,578 queries -- well
inside the stated budget of 4,194,304 for the live instance, and the same
bound (~2^(t/2+1)) will hold for any fresh instance generated the same way
with the same t.

All requests are batched (up to 200000 ops per HTTP round trip) to save
round trips; queries are read from the live GET /instance response, never
hard-coded.
"""
from __future__ import annotations

import math

from oracle_client import Oracle, OracleError

MAX_BATCH = 200000


def chain_mul(o: Oracle, start_label: str, step_label: str, count: int):
    """Return labels [start, start*step, start*step^2, ..., start*step^(count-1)]

    using `count - 1` multiply queries (the first label is free -- it is
    already known), batched in chunks of at most MAX_BATCH ops.
    """
    labels = [start_label]
    remaining = count - 1
    cur = start_label
    while remaining > 0:
        n = min(remaining, MAX_BATCH)
        ops = []
        # first op in the batch multiplies the last known literal label
        ops.append(["mul", cur, step_label])
        for i in range(1, n):
            ops.append(["mul", f"${i - 1}", step_label])
        results = o.query(ops)
        labels.extend(results)
        cur = results[-1]
        remaining -= n
    return labels


def bsgs(o: Oracle, g: str, h: str, t: int) -> int:
    m = 1 << ((t + 1) // 2)  # ceil(t/2), so m*m >= 2^t

    # Baby steps: g^0, g^1, ..., g^(m-1)
    g0 = o.exp(g, 0)  # identity, 1 query
    baby_labels = chain_mul(o, g0, g, m)  # m-1 more queries
    baby = {lab: j for j, lab in enumerate(baby_labels)}

    # Giant steps: h, h*g^-m, h*g^-2m, ...
    gm_inv = o.exp(g, -m)  # 1 query
    giant_labels_start = h
    remaining = m
    cur = giant_labels_start
    i = 0
    # check i = 0 first (free, no query needed to know the label)
    if cur in baby:
        j = baby[cur]
        return (i * m + j)
    i = 1
    remaining = m - 1
    while remaining > 0:
        n = min(remaining, MAX_BATCH)
        ops = []
        ops.append(["mul", cur, gm_inv])
        for k in range(1, n):
            ops.append(["mul", f"${k - 1}", gm_inv])
        results = o.query(ops)
        for k, lab in enumerate(results):
            if lab in baby:
                j = baby[lab]
                return ((i + k) * m + j)
        cur = results[-1]
        i += n
        remaining -= n

    raise RuntimeError("BSGS failed to find a match within the expected range")


def main():
    o = Oracle()
    inst = o.instance
    t = int(inst["params"]["t"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]

    x = bsgs(o, g, h, t)

    ok = o.submit(x)
    print(f"x = {x}")
    print(f"submit correct = {ok}")
    print(f"queries_used = {o.queries_used} / budget = {o.budget}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
