"""Instance generator: (rung, level, secret seed) -> DL instance with certified difficulty.

`level` L is the log2 of the target optimal query cost; the realised Q*_UB (exact worst-case
cost of the reference attack) lands near 2^L and is what every analysis uses.

Rungs
  1  smooth order:  N = q * S, q prime of 2L-2 bits, S a ~20-bit product of small prime powers;
                    x uniform in [0, N).                     Q* ~ 2 sqrt(q)     LB: M = q
  2  short exponent: N a 128-bit prime, x uniform in [0, 2^t), t = 2L-2.
                                                             Q* ~ 2^(t/2+1)     LB: M = 2^t
  3  combined:      N = S * P, P a 96-bit prime, S ~20-bit smooth; x uniform in [0, 2^t),
                    t = (2L-3) + bits(S).                    Q* ~ PH(S) + 2 sqrt(2^t/S)
                                                                                LB: M = floor(2^t/S)
  4  auxiliary input: p prime with d | p-1 (d a 14-bit prime), x uniform in [1, p),
                    publish g^x and g^(x^d).                 Q* ~ 2 sqrt(p/d) + 2 sqrt(d)
                                                                                LB: M = p-1, delta = d
Every instance also records the cost of the best *structure-ignoring* generic attack and the
generic success-probability bound at budget B for an attacker restricted to it.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from . import bounds
from .nt import ceil_sqrt, factorize, is_prime, random_prime

BUDGET_FACTOR = 4
LEVELS = {1: [8, 11, 14, 17, 20], 2: [8, 11, 14, 17, 20], 3: [8, 11, 14, 17, 20], 4: [11, 14, 17, 20]}
SMOOTH_BITS = 20
SMALL_POOL = [p for p in range(2, 100) if is_prime(p)]


@dataclass
class Instance:
    rung: int
    level: int
    N: int
    x: int
    published: dict[str, int]  # label name -> exponent (secret)
    keygen: str  # public description of how x (and any extra element) is generated
    params: dict  # public parameters shown to the agent besides N
    secret_structure: dict  # the planted structure (never shown to the agent)
    q_ub: int  # exact worst-case query cost of the reference attack (incl. submission)
    q_lb: int  # generic lower bound for success probability >= 1/2
    naive_cost: int  # worst-case cost of the structure-ignoring generic attack
    budget: int = 0
    meta: dict = field(default_factory=dict)

    def public_info(self) -> dict:
        return {"rung_id": f"ggm-dl-{self.rung}", "keygen": self.keygen, "params": self.params}


def _smooth_part(rng: random.Random, bits: int) -> dict[int, int]:
    f: dict[int, int] = {}
    S = 1
    while S.bit_length() < bits:
        q = rng.choice(SMALL_POOL)
        if (S * q).bit_length() > bits + 1:
            continue
        f[q] = f.get(q, 0) + 1
        S *= q
    return dict(sorted(f.items()))


def _prod(f: dict[int, int]) -> int:
    out = 1
    for q, e in f.items():
        out *= q ** e
    return out


def generate(rung: int, level: int, seed: bytes | int) -> Instance:
    if isinstance(seed, int):
        seed = seed.to_bytes(16, "big")
    rng = random.Random(hashlib.sha256(b"ggmbench|%d|%d|" % (rung, level) + seed).digest())
    L = level
    if rung == 1:
        q = random_prime(2 * L - 2, rng)
        S = _smooth_part(rng, SMOOTH_BITS)
        factors = {**S, q: 1}
        N = _prod(factors)
        x = rng.randrange(N)
        inst = Instance(
            rung, L, N, x, {"g": 1, "h": x},
            keygen="x is sampled uniformly at random from [0, N).",
            params={},
            secret_structure={"factorization": {str(k): v for k, v in factors.items()}, "q_max": q},
            q_ub=bounds.ph_cost(factors) + 1,
            q_lb=bounds.lb_queries(q),
            naive_cost=bounds.bsgs_cost(N) + 1,
        )
    elif rung == 2:
        N = random_prime(128, rng)
        t = 2 * L - 2
        x = rng.randrange(1 << t)
        inst = Instance(
            rung, L, N, x, {"g": 1, "h": x},
            keygen=f"x is sampled uniformly at random from [0, 2^{t}).",
            params={"t": t},
            secret_structure={"interval_bits": t},
            q_ub=bounds.bsgs_cost(1 << t) + 1,
            q_lb=bounds.lb_queries(1 << t),
            naive_cost=bounds.bsgs_cost(N) + 1,
        )
    elif rung == 3:
        S_f = _smooth_part(rng, SMOOTH_BITS)
        S = _prod(S_f)
        P = random_prime(96, rng)
        N = S * P
        t = (2 * L - 3) + S.bit_length()
        x = rng.randrange(1 << t)
        Wp = -(-(1 << t) // S)
        inst = Instance(
            rung, L, N, x, {"g": 1, "h": x},
            keygen=f"x is sampled uniformly at random from [0, 2^{t}).",
            params={"t": t},
            secret_structure={"smooth_part": {str(k): v for k, v in S_f.items()}, "S": S, "P": P,
                              "residual_interval": Wp},
            q_ub=bounds.ph_cost(S_f) + 3 + bounds.bsgs_cost(Wp) + 1,
            q_lb=bounds.lb_queries((1 << t) // S),
            # best attack using only one of the two structures: interval search over 2^t
            naive_cost=bounds.bsgs_cost(1 << t) + 1,
        )
    elif rung == 4:
        d = random_prime(14, rng)
        n1_target = (2 ** (L - 1) - ceil_sqrt(d)) ** 2
        while True:
            k = rng.randrange(n1_target // 2, n1_target * 3 // 2) & ~1  # even, so p = d*k+1 is odd
            p = d * k + 1
            if is_prime(p):
                break
        x = rng.randrange(1, p)
        inst = Instance(
            rung, L, p, x, {"g": 1, "h": x, "h_d": pow(x, d, p)},
            keygen=(f"x is sampled uniformly at random from [1, N). In addition to h = g^x, the "
                    f"challenger publishes h_d = g^(x^{d}), i.e. g raised to x^d mod N, for d = {d}."),
            params={"d": d},
            secret_structure={"d": d, "(p-1)/d": k, "p-1_factorization":
                              {str(a): b for a, b in factorize(p - 1).items()}},
            q_ub=bounds.cheon_cost(p, d) + 1,
            q_lb=bounds.lb_queries(p - 1, k0=3, delta=d),
            naive_cost=bounds.bsgs_cost(p) + 1,
        )
    else:
        raise ValueError(rung)
    inst.budget = BUDGET_FACTOR * inst.q_ub
    inst.meta = {
        "log2_q_ub": _log2(inst.q_ub), "log2_q_lb": _log2(inst.q_lb),
        "log2_naive": _log2(inst.naive_cost), "log2_budget": _log2(inst.budget),
        "ub_over_lb": inst.q_ub / max(1, inst.q_lb),
        "naive_over_budget": inst.naive_cost / inst.budget,
    }
    return inst


def _log2(v: int) -> float:
    import math
    return math.log2(v) if v > 0 else float("-inf")
