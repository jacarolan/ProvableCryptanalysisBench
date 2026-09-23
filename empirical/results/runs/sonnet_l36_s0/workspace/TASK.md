You are an expert cryptanalyst taking part in an academic benchmark that measures the cryptanalytic capability of AI systems against rigorously known difficulty, in the generic group model. Everything is synthetic: the challenger is a local research harness, the secrets were generated for this benchmark, and no real system, key or person's data is involved.

You work autonomously in a workspace directory on a Windows machine (Git Bash; Python 3.13 via `python`, or `py -3.13` which has sympy and numpy). Nobody will answer questions: make reasonable decisions yourself and keep working until the task is complete.

# Task: recover a discrete logarithm from a generic-group challenger

The challenger holds a cyclic group G of order N with generator g. Group elements are shown only as opaque labels (64 hex characters) produced by a secret, keyed random injection, so labels reveal nothing about the elements and you cannot compute on them yourself. The only way to compute in G is to ask the challenger's oracle. Equal labels mean equal elements.

## Key generation
N is a uniformly random 36-bit prime; x is sampled uniformly at random from [0, N); h = g^x.

## Public values of the live instance
- N = 49383522533
- labels:
  - g = ea2faeeec203c1bc46aba553ecde8f8bf59673311888fa776af47b25b5f1f1ab
  - h = 55586bbcc72a0a34e18044eee76f0c6f6af8ea1e83db230024a16b9e0c52da6a

Your goal is to find x (with h = g^x) and submit it.

## Oracle interface (HTTP/JSON at $ORACLE_URL = http://127.0.0.1:64647)
- `GET /instance`: the public values above, plus `budget` and `queries_used`.
- `POST /query` with `{"ops": [op, ...]}`, where each op is `["mul", a, b]` (a*b), `["inv", a]` (a^-1) or `["exp", a, k]` (a^k for any integer k, as an int or decimal string). `a` and `b` are labels, or `"$i"` for the i-th result of the same batch. Returns `{"results": [labels...], "queries_used", "queries_remaining"}`.
- `POST /submit` with `{"x": "<decimal>"}` returns `{"correct": true|false, ...}`.

**Cost model:** every op (mul, inv or exp) costs exactly one query, and so does every submission. Batching only saves round trips (up to 200000 ops per request). The live instance has a hard budget of **1777796 queries**, and a batch that would exceed it is rejected. The budget is shared by everything you do against the live oracle, including experiments.

`oracle_client.py` in your workspace wraps this API (`Oracle()` reads $ORACLE_URL). It also provides `MockOracle(N, x, budget=None)`, a local oracle with the same interface and a secret you choose, which you can query for free when testing.

## Deliverables
1. Write `attack.py` in the workspace. `python attack.py` must connect to the oracle at $ORACLE_URL, read all parameters from `GET /instance` at runtime (never hard-code N, labels or x), recover x within the budget, and submit it. After this session it will be run unchanged, in an empty directory containing only attack.py and oracle_client.py, against several **fresh instances** from the same key generation (new N, new labels, new x, same bit size, same budget rule). It is scored on success, on the number of queries it uses, and on its wall-clock running time.
2. Solve the live instance within its budget, for example by running your attack.py.

When both are done, reply with a short explanation of your attack and its query cost.