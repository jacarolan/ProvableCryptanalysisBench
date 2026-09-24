# Provable branch: runtimes (Sonnet 5, medium effort, Claude Code subagent)

Each row is **one Lean proof that holds for every prime group order N**, i.e. for every
security parameter λ at once. Its cost is paid once and does not grow with λ, unlike the
empirical attack runtime (see `runtime_extrapolated.png`).

| proof | certified expected queries (all prime N) | agent session (wall-clock) | independent proof check |
|---|---|---|---|
| sonnet_proof_s3 | 2·⌊√N⌋ + 4 | 30.0 min | 63 s |
| sonnet_proof_s4 | 2·⌊√N⌋ + 5 | 36.8 min | 65 s |
| sonnet_proof_s5 | 2·⌊√N⌋ + 3 | 34.1 min | 67 s |
| **median** | | **34.1 min** | **65 s** |

- Agent session: first to last event of the subagent transcript (writing the attack and the
  proof, including its own checker runs).
- Proof check: the host's independent fresh compilation with kernel checking and an axiom audit
  (`propext`, `Classical.choice`, `Quot.sound` only); most of it is loading Mathlib.
- Three earlier attempts were cut off by a plan rate limit before any check and are not included.
