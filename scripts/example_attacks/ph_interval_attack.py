"""Self-contained example attack.py (uses only oracle_client.py): Pohlig-Hellman on the small
factors of N, then baby-step giant-step over the remaining interval. Solves rungs 1-3.
Used to smoke-test the harness's replay path without calling any model."""
import math
from oracle_client import Oracle

o = Oracle()
N = int(o.instance["N"]); g = o.instance["labels"]["g"]; h = o.instance["labels"]["h"]
t = o.instance.get("params", {}).get("t")
X = (1 << int(t)) if t is not None else N

def factor(n, bound=1 << 21):
    f, p = {}, 2
    while p * p <= n and p < bound:
        while n % p == 0: f[p] = f.get(p, 0) + 1; n //= p
        p += 1
    return f, n

def qall(ops, c=65536):
    out = []
    for i in range(0, len(ops), c): out += o.query(ops[i:i + c])
    return out

def bsgs(G, H, W):
    m = math.isqrt(W - 1) + 1
    table = dict(zip(qall([["exp", G, j] for j in range(m)]), range(m)))
    if H in table: return table[H]
    stride, cur, i = o.exp(G, -m), H, 0
    while i * m < W:
        n = min(4096, -(-W // m) - i)
        labs = o.query([["mul", cur, stride]] + [["mul", f"${k}", stride] for k in range(n - 1)])
        for k, lab in enumerate(labs):
            if lab in table: return (i + k + 1) * m + table[lab]
        cur, i = labs[-1], i + n
    raise RuntimeError("not found")

small, rest = factor(N)
if rest > 1 and rest < (1 << 44) and all(rest % p for p in range(2, 1000)):  # rest is a moderate prime
    small[rest] = 1; rest = 1
r, S = 0, 1
for q, e in small.items():
    gq = o.exp(g, N // q ** e); hq = o.exp(h, N // q ** e)
    xq = bsgs(gq, hq, q ** e)
    r += S * ((xq - r) * pow(S, -1, q ** e) % (q ** e)); S *= q ** e
if S == N:
    x = r
else:
    G = o.exp(g, S); Hr = o.query([["exp", g, -r], ["mul", h, "$0"]])[1]
    x = r + S * bsgs(G, Hr, -(-(X - r) // S))
print("x =", x, "correct:", o.submit(x), "queries:", o.queries_used)
