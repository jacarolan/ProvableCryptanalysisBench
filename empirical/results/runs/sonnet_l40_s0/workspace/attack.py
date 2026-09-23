"""
Baby-step / giant-step attack on the generic-group discrete-log oracle.

The group has prime order N (~40-bit). We recover x such that h = g^x by:

  1. Baby steps:  baby[j] = g^j          for j = 0 .. m-1
  2. Giant steps: giant[i] = h * g^(-m*i) for i = 0 .. m-1
  3. Find a collision baby[j] == giant[i]  =>  h * g^(-m i) = g^j
                                            =>  h = g^(j + m i)
                                            =>  x = j + m*i  (mod N)

with m = ceil(sqrt(N)), guaranteeing a collision exists since 0 <= x < N <= m*m.

Every group operation costs one oracle query. Steps are generated as chained
"mul" operations inside large batches (up to 200000 ops per HTTP request) so
that the O(sqrt(N)) query cost is paid in very few round trips, keeping wall
clock low. Total queries ~= 2*ceil(sqrt(N)) + O(1), comfortably inside the
budget (~1.66M queries for a 40-bit N vs a budget of ~6.6M).
"""

from __future__ import annotations

import math
import os
import sys

from oracle_client import Oracle, OracleError

MAX_OPS_PER_BATCH = 200000


def chain_mul(oracle: Oracle, start_label: str, step_label: str, count: int):
    """Return [start*step^1, start*step^2, ..., start*step^count] (count labels),
    i.e. the result of repeatedly multiplying by step_label, count times,
    starting from start_label. Uses batched requests internally."""
    out = []
    cur = start_label
    remaining = count
    while remaining > 0:
        batch_n = min(remaining, MAX_OPS_PER_BATCH)
        ops = []
        for k in range(batch_n):
            a = cur if k == 0 else f"${k - 1}"
            ops.append(["mul", a, step_label])
        results = oracle.query(ops)
        out.extend(results)
        cur = results[-1]
        remaining -= batch_n
    return out


def bsgs(oracle: Oracle, N: int, g: str, h: str) -> int:
    m = math.isqrt(N - 1) + 1  # ceil(sqrt(N))
    while m * m < N:
        m += 1

    # Baby steps: baby_dict[label] = j, for j = 0 .. m-1
    baby_dict = {}
    identity = oracle.exp(g, 0)
    baby_dict[identity] = 0
    if m > 1:
        baby_labels = chain_mul(oracle, identity, g, m - 1)  # g^1 .. g^(m-1)
        for j, lab in enumerate(baby_labels, start=1):
            if lab not in baby_dict:
                baby_dict[lab] = j

    # factor = g^(-m)
    factor = oracle.exp(g, -m)

    # Giant steps: giant[i] = h * factor^i, i = 0 .. m-1
    # i = 0 is just h itself.
    if h in baby_dict:
        j = baby_dict[h]
        x = (j + m * 0) % N
        return x

    if m > 1:
        giant_labels = chain_mul(oracle, h, factor, m - 1)  # i = 1 .. m-1
        for i, lab in enumerate(giant_labels, start=1):
            if lab in baby_dict:
                j = baby_dict[lab]
                x = (j + m * i) % N
                return x

    raise RuntimeError("BSGS failed to find a collision (unexpected)")


def main():
    oracle = Oracle()
    inst = oracle.instance
    N = int(inst["N"])
    labels = inst["labels"]
    g = labels["g"]
    h = labels["h"]

    print(f"N = {N} (~{N.bit_length()} bits); budget = {oracle.budget}", file=sys.stderr)

    x = bsgs(oracle, N, g, h)

    print(f"Recovered x = {x}; queries used = {oracle.queries_used}", file=sys.stderr)

    ok = oracle.submit(x)
    print(f"submit -> correct = {ok}; total queries used = {oracle.queries_used}", file=sys.stderr)

    if not ok:
        print("ATTACK FAILED", file=sys.stderr)
        sys.exit(1)

    print(x)


if __name__ == "__main__":
    main()
