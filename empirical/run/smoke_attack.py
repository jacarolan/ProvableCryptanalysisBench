"""Pipeline smoke test only (not a result): textbook BSGS against the live oracle."""
import math
from oracle_client import Oracle
o = Oracle(); N = int(o.instance["N"]); g, h = o.instance["labels"]["g"], o.instance["labels"]["h"]
m = math.isqrt(N - 1) + 1
tab = {}
for i in range(0, m, 100000):
    js = list(range(i, min(m, i + 100000)))
    tab.update(zip(o.query([["exp", g, j] for j in js]), js))
stride, cur, i = o.exp(g, -m), h, 0
while True:
    if cur in tab: x = i * m + tab[cur]; break
    n = 4096
    labs = o.query([["mul", cur, stride]] + [["mul", f"${k}", stride] for k in range(n - 1)])
    hit = next(((k, l) for k, l in enumerate(labs) if l in tab), None)
    if hit: x = (i + hit[0] + 1) * m + tab[hit[1]]; break
    cur, i = labs[-1], i + n
print("x", x, o.submit(x), o.queries_used)
