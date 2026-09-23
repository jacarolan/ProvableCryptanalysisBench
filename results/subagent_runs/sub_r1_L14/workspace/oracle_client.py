"""Client for the generic-group challenger (stdlib only).

    from oracle_client import Oracle, MockOracle
    o = Oracle()                       # live challenger at $ORACLE_URL
    inst = o.instance                  # dict: N (decimal string), labels {"g", "h", ...}, params, keygen, budget
    a = o.mul(l1, l2)                  # label of l1*l2            (1 query)
    b = o.inv(l1)                      # label of l1^-1            (1 query)
    c = o.exp(l1, k)                   # label of l1^k, k any int  (1 query)
    labs = o.query([["exp", g, 5], ["mul", "$0", h], ["inv", "$1"]])   # batch; "$i" = i-th result of this batch
    ok = o.submit(x)                   # True iff x is the discrete log of h to base g   (1 query)
    o.queries_used, o.budget

Every group operation (mul / inv / exp) and every submission costs exactly one query, whether sent
alone or in a batch. Batches (up to 200000 ops) only save HTTP round trips. Comparing labels is
free: two labels are equal iff the group elements are equal.

MockOracle(N, x, budget=None, aux_powers=()) has the same interface but runs locally with a secret
you choose, for free testing. aux_powers=(d,) additionally publishes labels["h_d"] = g^(x^d mod N).
"""
from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.request


class OracleError(RuntimeError):
    pass


class Oracle:
    def __init__(self, url: str | None = None):
        self.url = (url or os.environ["ORACLE_URL"]).rstrip("/")
        self.instance = self._call("GET", "/instance")
        self.budget = int(self.instance["budget"])
        self.queries_used = int(self.instance["queries_used"])

    def _call(self, method, path, obj=None):
        data = json.dumps(obj).encode() if obj is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise OracleError(f"HTTP {e.code}: {e.read().decode(errors='replace')}") from None

    def query(self, ops):
        ops = [[op[0], *[str(a) if not isinstance(a, str) else a for a in op[1:]]] for op in ops]
        r = self._call("POST", "/query", {"ops": ops})
        self.queries_used = r["queries_used"]
        return r["results"]

    def mul(self, a, b):
        return self.query([["mul", a, b]])[0]

    def inv(self, a):
        return self.query([["inv", a]])[0]

    def exp(self, a, k):
        return self.query([["exp", a, int(k)]])[0]

    def submit(self, x) -> bool:
        r = self._call("POST", "/submit", {"x": str(int(x))})
        self.queries_used = r["queries_used"]
        return r["correct"]


class MockOracle(Oracle):
    """Local stand-in with a known secret. Labels are random strings, as in the real oracle."""

    def __init__(self, N: int, x: int, budget: int | None = None, aux_powers=()):
        self.N, self._x = int(N), int(x) % int(N)
        self._lab, self._elt = {}, {}
        labels = {"g": self._enc(1), "h": self._enc(self._x)}
        for d in aux_powers:
            labels["h_d" if len(aux_powers) == 1 else f"h_{d}"] = self._enc(pow(self._x, d, self.N))
        self.budget = budget if budget is not None else 10 ** 12
        self.queries_used = 0
        self.instance = {"N": str(self.N), "labels": labels, "budget": self.budget, "queries_used": 0,
                         "params": {"d": aux_powers[0]} if len(aux_powers) == 1 else {},
                         "keygen": "mock"}

    def _enc(self, e):
        e %= self.N
        if e not in self._lab:
            s = secrets.token_hex(32)
            self._lab[e], self._elt[s] = s, e
        return self._lab[e]

    def query(self, ops):
        if self.queries_used + len(ops) > self.budget:
            raise OracleError("HTTP 429: budget exceeded")
        vals, out = [], []
        for op in ops:
            arg = lambda a: vals[int(a[1:])] if isinstance(a, str) and a.startswith("$") else self._elt[a]
            if op[0] == "mul":
                v = arg(op[1]) + arg(op[2])
            elif op[0] == "inv":
                v = -arg(op[1])
            elif op[0] == "exp":
                v = arg(op[1]) * int(op[2])
            else:
                raise OracleError(f"HTTP 400: malformed op {op!r}")
            vals.append(v % self.N)
            out.append(self._enc(v))
        self.queries_used += len(ops)
        return out

    def submit(self, x) -> bool:
        self.queries_used += 1
        return int(x) % self.N == self._x
