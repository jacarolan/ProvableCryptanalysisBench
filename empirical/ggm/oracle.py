"""The generic-group challenger.

Model (Shoup/Maurer-style GGM with a keyed random encoding):

* The group is Z_N (additive), abstractly a cyclic group <g> of order N; element e <-> g^e.
* Every element is shown to the adversary only through a label sigma(e): a keyed pseudorandom
  permutation of a 256-bit block (e || 0^128), so labels are 64 hex chars, injective, and carry
  no information about e. Decoding checks the zero padding, so labels the adversary never
  received are rejected (except with probability 2^-128).
* One query = one new group element: mul(a,b) = sigma(e_a + e_b), inv(a) = sigma(-e_a),
  exp(a,k) = sigma(k*e_a) for a public integer k. Equality testing is free (compare labels).
  A submission of a candidate x is an equality test against h and also costs one query.
* Queries are counted and a hard budget is enforced (a batch that would exceed it is rejected
  without being executed).

Charging exp at 1 is the natural unit for the lower bounds: every bound in THEORY.md counts the
number of group elements the adversary obtains, which is at most one per query regardless of
which operation produced it. (An op-only model would charge exp ~1.5 log2 k multiplications;
the lower bounds are unchanged and the upper bounds pick up that log factor.)
"""
from __future__ import annotations

import hashlib
import os
import threading
import time

_HALF = 16  # bytes per Feistel half (128 bits)
_ROUNDS = 4  # Luby-Rackoff: 4 rounds of a PRF give a strong PRP


class Encoding:
    """Keyed pseudorandom permutation on 256-bit blocks, used as sigma: Z_N -> labels."""

    def __init__(self, key: bytes, N: int):
        assert N < 1 << (8 * _HALF)
        self.N = N
        self._rk = [hashlib.blake2b(key, person=b"ggmbench-rk" + bytes([i]), digest_size=32).digest()
                    for i in range(_ROUNDS)]

    def _f(self, i: int, r: bytes) -> int:
        return int.from_bytes(hashlib.blake2b(r, key=self._rk[i], digest_size=_HALF).digest(), "big")

    def encode(self, e: int) -> str:
        L, R = e % self.N, 0
        for i in range(_ROUNDS):
            L, R = R, L ^ self._f(i, R.to_bytes(_HALF, "big"))
        return (L.to_bytes(_HALF, "big") + R.to_bytes(_HALF, "big")).hex()

    def decode(self, label: str) -> int:
        try:
            raw = bytes.fromhex(label)
        except (ValueError, TypeError):
            raise BadLabel(label)
        if len(raw) != 2 * _HALF:
            raise BadLabel(label)
        L, R = int.from_bytes(raw[:_HALF], "big"), int.from_bytes(raw[_HALF:], "big")
        for i in reversed(range(_ROUNDS)):
            L, R = R ^ self._f(i, L.to_bytes(_HALF, "big")), L
        if R != 0 or L >= self.N:
            raise BadLabel(label)
        return L


class BadLabel(ValueError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class GroupOracle:
    """Holds one DL instance: the group order, the secret x, auxiliary exponents, the budget.

    `public` is everything the adversary may see; `secret_exponents` maps each published label
    name to its (secret) exponent, e.g. {"g": 1, "h": x, "h_d": x^d mod p}.
    """

    MAX_BATCH = 200_000

    def __init__(self, N: int, x: int, published: dict[str, int], budget: int,
                 public_info: dict, key: bytes | None = None):
        self.N = N
        self.x = x
        self.budget = budget
        self.enc = Encoding(key or os.urandom(32), N)
        self.labels = {name: self.enc.encode(e) for name, e in published.items()}
        self.public_info = dict(public_info)
        self.queries_used = 0
        self.solved_at: int | None = None  # queries_used at first correct submission
        self.submissions: list[dict] = []
        self.batch_log: list[tuple[float, int]] = []  # (time, n_ops)
        self.t0 = time.time()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ public API
    def instance(self) -> dict:
        return {**self.public_info, "N": str(self.N), "labels": dict(self.labels),
                "budget": self.budget, "queries_used": self.queries_used}

    def query(self, ops: list) -> list[str]:
        if not isinstance(ops, list):
            raise ValueError("ops must be a list")
        if len(ops) > self.MAX_BATCH:
            raise ValueError(f"at most {self.MAX_BATCH} ops per batch")
        with self._lock:
            if self.queries_used + len(ops) > self.budget:
                raise BudgetExceeded(
                    f"batch of {len(ops)} ops would exceed budget "
                    f"({self.queries_used} used of {self.budget})")
            N, enc = self.N, self.enc
            vals: list[int] = []
            out: list[str] = []

            def arg(a):
                if isinstance(a, str) and a.startswith("$"):
                    i = int(a[1:])
                    if not 0 <= i < len(vals):
                        raise ValueError(f"bad back-reference {a}")
                    return vals[i]
                return enc.decode(a)

            for op in ops:
                if not isinstance(op, (list, tuple)) or not op:
                    raise ValueError(f"malformed op {op!r}")
                name = op[0]
                if name == "mul" and len(op) == 3:
                    v = (arg(op[1]) + arg(op[2])) % N
                elif name == "inv" and len(op) == 2:
                    v = (-arg(op[1])) % N
                elif name == "exp" and len(op) == 3:
                    v = (arg(op[1]) * int(op[2])) % N
                else:
                    raise ValueError(f"malformed op {op!r}")
                vals.append(v)
                out.append(enc.encode(v))
            self.queries_used += len(ops)
            self.batch_log.append((time.time() - self.t0, len(ops)))
            return out

    def submit(self, x) -> bool:
        with self._lock:
            if self.queries_used + 1 > self.budget:
                raise BudgetExceeded(f"budget exhausted ({self.queries_used} of {self.budget})")
            self.queries_used += 1
            ok = int(x) % self.N == self.x % self.N
            self.submissions.append({"t": time.time() - self.t0, "q": self.queries_used, "correct": ok})
            if ok and self.solved_at is None:
                self.solved_at = self.queries_used
            return ok

    # ------------------------------------------------------------------ bookkeeping
    def result(self) -> dict:
        return {"solved": self.solved_at is not None, "queries_at_solve": self.solved_at,
                "queries_used": self.queries_used, "budget": self.budget,
                "submissions": self.submissions, "n_batches": len(self.batch_log),
                "batch_log": self.batch_log[-2000:]}


class LocalClient:
    """In-process client with the same interface as the HTTP client (used by reference solvers)."""

    def __init__(self, oracle: GroupOracle):
        self.o = oracle
        self.instance = oracle.instance()

    def query(self, ops):
        return self.o.query(ops)

    def submit(self, x):
        return self.o.submit(x)

    @property
    def queries_used(self):
        return self.o.queries_used
