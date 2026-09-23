"""Baby-step giant-step attack on a generic cyclic group of known prime order N.

Recovers x with h = g^x by:
  1. Baby steps: labels of g^0, g^1, ..., g^(m-1), stored in a dict label -> j.
     Computed with one batched query of m ops (1 exp for g^0, then m-1 muls
     chaining off the previous result via "$i" references).
  2. factor = g^(-m)  (1 exp query).
  3. Giant steps: y_0 = h (free, already known), y_i = y_{i-1} * factor for
     i = 1..m-1 (m-1 batched mul queries). After each step, check y_i against
     the baby-step dictionary (label equality is free/local).
  4. If y_i == g^j, then h * g^(-i*m) = g^j, so x = (j + i*m) mod N.

m = ceil(sqrt(N)) makes j and i both range over [0, m), covering every
x in [0, N) since N <= m*m. Total oracle ops: m (baby) + 1 (factor) + (m-1)
(giant) = 2m, i.e. about 2*sqrt(N) -- for a 28-bit N (~1.8e8) that's roughly
27,000 queries, comfortably inside the stated ~107k budget.
"""
from __future__ import annotations

import math
import os
import sys

from oracle_client import Oracle, OracleError


def bsgs(o: Oracle, N: int, g: str, h: str) -> int:
    m = math.isqrt(N) + 1  # ceil-ish; m*m >= N

    # --- Baby steps: g^0 .. g^(m-1) in one batch ---
    ops = [["exp", g, 0]]
    for j in range(1, m):
        ops.append(["mul", f"${j - 1}", g])
    # Append factor = g^-m to the same batch to save a round trip.
    ops.append(["exp", g, -m])

    labels = o.query(ops)
    baby_labels = labels[:m]
    factor = labels[m]

    baby = {lab: j for j, lab in enumerate(baby_labels)}

    # Check i = 0 for free using the known h label.
    if h in baby:
        return baby[h] % N

    # --- Giant steps: y_i = h * factor^i for i = 1 .. m-1 ---
    ops2 = [["mul", h, factor]]
    for i in range(2, m):
        ops2.append(["mul", f"${i - 2}", factor])

    giant_labels = o.query(ops2)
    for idx, lab in enumerate(giant_labels):
        i = idx + 1
        if lab in baby:
            j = baby[lab]
            x = (j + i * m) % N
            return x

    raise RuntimeError("BSGS failed to find a match; unexpected for a correct group order N")


def main():
    o = Oracle()
    inst = o.instance
    N = int(inst["N"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]

    x = bsgs(o, N, g, h)

    ok = o.submit(x)
    print(f"N={N}")
    print(f"x={x}")
    print(f"correct={ok}")
    print(f"queries_used={o.queries_used} / budget={o.budget}")

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
