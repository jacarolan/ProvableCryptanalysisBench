"""Evaluate a kernel-exported bound without running an attack.

Three modes:
  --lams    harmonized with ../empirical: at each security parameter lam, draw random lam-bit primes
            with the same seeded procedure as empirical/ggm/instances.generate(lam, seed) and report the certified
            expected-query bound next to the empirical lower bound lb_expected(N) for that N.
            The primes are Miller-Rabin probable primes (as in empirical); the certificate is
            conditional on primality, which is not re-proved here.
  --bits    the monotone bound at 2^lam - 1, an upper envelope for every lam-bit prime.
  --orders  exact supplied orders, conditional on their primality.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
EMPIRICAL = ROOT.parent / "empirical"
DEFAULT_LAMS = [16, 20, 24, 28, 32, 36, 40, 64, 128, 256, 512, 1024, 2048, 4096]


def evaluate(expr: dict, p: int) -> Fraction:
    op = expr["op"]
    if op == "constant":
        return Fraction(expr["value"])
    if op == "order":
        return Fraction(p)
    if op == "sqrtOrder":
        return Fraction(math.isqrt(p))
    if op == "add":
        return evaluate(expr["a"], p) + evaluate(expr["b"], p)
    if op == "mul":
        return evaluate(expr["a"], p) * evaluate(expr["b"], p)
    if op == "div":
        # Lean's field division by zero is zero; preserve its exact semantics.
        den = expr["denominator"]
        return evaluate(expr["a"], p) / den if den else Fraction(0)
    raise ValueError(f"Unknown bound node: {op}")


def _empirical():
    """Import the empirical prime sampler and lower bound (single source of truth)."""
    if str(EMPIRICAL) not in sys.path:
        sys.path.append(str(EMPIRICAL))  # append: provable/run must shadow empirical/run
    from ggm.instances import lb_expected  # noqa: E402
    from ggm.nt import random_prime  # noqa: E402
    return random_prime, lb_expected


PRIME_CACHE = ROOT / "results" / "primes.json"


def sample_order(lam: int, seed: int) -> int:
    """The group order N that empirical/ggm/instances.generate(lam, seed) draws (same seeded RNG),
    without the float conversion that overflows beyond ~1024 bits. Cached: 4096-bit primes are slow."""
    import hashlib
    import random
    cache = json.loads(PRIME_CACHE.read_text()) if PRIME_CACHE.is_file() else {}
    key = f"{lam}:{seed}"
    if key not in cache:
        random_prime, _ = _empirical()
        rng = random.Random(hashlib.sha256(b"ggm-dl|%d|" % lam + seed.to_bytes(16, "big")).digest())
        cache[key] = str(random_prime(lam, rng))
        PRIME_CACHE.parent.mkdir(parents=True, exist_ok=True)
        PRIME_CACHE.write_text(json.dumps(cache, indent=0))
    return int(cache[key])


def _log2(q: Fraction) -> float:
    return math.log2(q.numerator) - math.log2(q.denominator) if q > 0 else float("-inf")


def evaluate_lams(bound: dict, lams: list[int], samples: int = 3) -> list[dict]:
    _, lb_expected = _empirical()
    rows = []
    for lam in lams:
        for seed in range(samples):
            N = sample_order(lam, 10_000 + seed)  # fixed public seeds
            b, lb = evaluate(bound, N), lb_expected(N)
            rows.append({"lam": lam, "seed": seed, "N": str(N), "prime_check": "Miller-Rabin probable prime",
                         "certified_expected_queries": str(b), "log2_certified": _log2(b),
                         "lb_expected": str(lb), "log2_lb_expected": _log2(lb),
                         "log2_certified_over_lb": _log2(b / lb) if lb > 0 else None})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("check_json", type=Path)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--lams", type=int, nargs="*")
    group.add_argument("--orders", type=int, nargs="+")
    group.add_argument("--bits", type=int, nargs="+")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    record = json.loads(a.check_json.read_text(encoding="utf-8"))
    if record["status"] != "accepted":
        ap.error("Cannot evaluate a rejected certificate")
    bound = record["certificate"]["bound"]
    if a.lams is not None:
        rows = evaluate_lams(bound, a.lams or DEFAULT_LAMS, a.samples)
    else:
        if a.bits and any(not 2 <= n <= 4096 for n in a.bits):
            ap.error("Bit lengths must be in [2,4096]")
        if a.orders and any(n < 2 for n in a.orders):
            ap.error("Orders must be at least 2")
        rows = []
        for p in a.orders or [(1 << n) - 1 for n in a.bits]:
            value = evaluate(bound, p)
            rows.append({"lam": p.bit_length(), "order_or_envelope_endpoint": str(p),
                         "expected_query_upper_bound": {"numerator": str(value.numerator),
                                                        "denominator": str(value.denominator)},
                         "meaning": "upper envelope for every lam-bit prime (monotone bound AST)" if a.bits else
                                    "conditional on supplied order being prime; primality not checked"})
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"source_sha256": record["source_sha256"], "rows": rows,
                                "attack_executed": False, "is_empirical_runtime": False}, indent=2), encoding="utf-8")
    print(a.out)


if __name__ == "__main__":
    main()
