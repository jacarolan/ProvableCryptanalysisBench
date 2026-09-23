"""Reference (optimal-up-to-constants) attacks, one per rung.

They use only public information (N, the keygen description's parameters, the labels) plus free
local computation, and talk to the oracle through a client with .instance / .query / .submit.
Their exact worst-case query counts are the Q*_UB formulas in bounds.py; verify_reference.py
checks every run against them.
"""
from __future__ import annotations

from .nt import ceil_div, ceil_sqrt, crt, factorize, primitive_root

FIRST_CHUNK = 64
MAX_CHUNK = 1 << 16


def _chunks(total: int):
    """Doubling chunk sizes summing to `total` (bounds overshoot past an early match)."""
    done, c = 0, FIRST_CHUNK
    while done < total:
        n = min(c, total - done)
        yield done, n
        done += n
        c = min(2 * c, MAX_CHUNK)


def query_all(client, ops: list) -> list[str]:
    """Send a long list of independent ops in several batches."""
    out: list[str] = []
    for i in range(0, len(ops), MAX_CHUNK):
        out += client.query(ops[i:i + MAX_CHUNK])
    return out


def baby_table(client, G: str, m: int) -> dict[str, int]:
    js = [j for j in range(m) if j != 1]
    labels = query_all(client, [["exp", G, j] for j in js])
    table = dict(zip(labels, js))
    if m >= 2:
        table[G] = 1
    return table


def giant_search(client, table: dict[str, int], H: str, stride: str | None, steps: int, m: int) -> int:
    """Find i*m + j with H * stride^i = table[j]; stride = G^(-m). Uses at most steps-1 queries."""
    if H in table:
        return table[H]
    cur = H
    for done, n in _chunks(steps - 1):
        ops = [["mul", cur, stride]] + [["mul", f"${k}", stride] for k in range(n - 1)]
        labs = client.query(ops)
        for k, lab in enumerate(labs):
            if lab in table:
                return (done + k + 1) * m + table[lab]
        cur = labs[-1]
    raise RuntimeError("BSGS failed: target not in range")


def bsgs(client, G: str, H: str, W: int) -> int:
    """k in [0, W) with H = G^k."""
    m = ceil_sqrt(W)
    table = baby_table(client, G, m)
    if H in table:
        return table[H]
    steps = ceil_div(W, m)
    if steps <= 1:
        raise RuntimeError("BSGS failed")
    stride = client.query([["exp", G, -m]])[0]
    return giant_search(client, table, H, stride, steps, m)


def pohlig_hellman(client, g: str, h: str, N: int, factors: dict[int, int]) -> tuple[int, int]:
    """Returns (x mod M, M) with M = prod q^e over `factors` (each q^e must divide N exactly)."""
    residues, moduli = [], []
    for q, e in factors.items():
        gamma = client.query([["exp", g, N // q]])[0]
        m = min(q, ceil_sqrt(e * q))
        table = baby_table(client, gamma, m)
        steps = ceil_div(q, m)
        stride = client.query([["exp", gamma, -m]])[0] if steps > 1 else None
        xk = 0
        for k in range(e):
            c = N // q ** (k + 1)
            if k == 0:
                target = client.query([["exp", h, c]])[0]
            else:
                target = client.query([["exp", h, c], ["exp", g, -xk * c], ["mul", "$0", "$1"]])[2]
            digit = giant_search(client, table, target, stride, steps, m)
            xk += digit * q ** k
        residues.append(xk)
        moduli.append(q ** e)
    M = 1
    for mod in moduli:
        M *= mod
    return crt(residues, moduli), M


def _public(client):
    inst = client.instance
    return int(inst["N"]), inst["labels"], inst.get("params", {})


def solve_rung1(client) -> int:
    N, lab, _ = _public(client)
    x, _ = pohlig_hellman(client, lab["g"], lab["h"], N, factorize(N))
    client.submit(x)
    return x


def solve_rung2(client) -> int:
    N, lab, params = _public(client)
    x = bsgs(client, lab["g"], lab["h"], 1 << int(params["t"]))
    client.submit(x)
    return x


def solve_rung3(client, max_small_prime: int = 1 << 20) -> int:
    N, lab, params = _public(client)
    g, h, X = lab["g"], lab["h"], 1 << int(params["t"])
    f = factorize(N)
    small = {q: e for q, e in f.items() if q <= max_small_prime}
    r, S = pohlig_hellman(client, g, h, N, small)
    G, _, Hr = client.query([["exp", g, S], ["exp", g, -r], ["mul", h, "$1"]])
    k = bsgs(client, G, Hr, ceil_div(X - r, S))
    x = r + S * k
    client.submit(x)
    return x


def solve_rung4(client) -> int:
    p, lab, params = _public(client)
    d = int(params["d"])
    g, h, hd = lab["g"], lab["h"], lab["h_d"]
    zeta = primitive_root(p, factorize(p - 1))
    n1 = (p - 1) // d
    # step 1: x^d = xi^k0, xi = zeta^d of order n1
    xi = pow(zeta, d, p)
    m1 = ceil_sqrt(n1)
    js = list(range(1, m1))
    table = dict(zip(query_all(client, [["exp", g, pow(xi, j, p)] for j in js]), js))
    table[g] = 0
    k0 = None
    if hd in table:
        k0 = table[hd]
    else:
        xi_inv_m = pow(xi, -m1, p)
        for done, n in _chunks(ceil_div(n1, m1) - 1):
            idx = range(done + 1, done + n + 1)
            labs = client.query([["exp", hd, pow(xi_inv_m, i, p)] for i in idx])
            hit = next(((i, lab_) for i, lab_ in zip(idx, labs) if lab_ in table), None)
            if hit:
                k0 = hit[0] * m1 + table[hit[1]]
                break
    assert k0 is not None
    # step 2: x = zeta^k0 * eta^l, eta = zeta^n1 of order d
    c = pow(zeta, k0, p)
    eta = pow(zeta, n1, p)
    m2 = ceil_sqrt(d)
    vs = list(range(m2))
    table2 = dict(zip(query_all(client, [["exp", g, c * pow(eta, v, p) % p] for v in vs]), vs))
    l = None
    if h in table2:
        l = table2[h]
    else:
        eta_inv_m = pow(eta, -m2, p)
        for done, n in _chunks(ceil_div(d, m2) - 1):
            idx = range(done + 1, done + n + 1)
            labs = client.query([["exp", h, pow(eta_inv_m, u, p)] for u in idx])
            hit = next(((u, lab_) for u, lab_ in zip(idx, labs) if lab_ in table2), None)
            if hit:
                l = hit[0] * m2 + table2[hit[1]]
                break
    assert l is not None
    x = c * pow(eta, l, p) % p
    client.submit(x)
    return x


SOLVERS = {1: solve_rung1, 2: solve_rung2, 3: solve_rung3, 4: solve_rung4}

