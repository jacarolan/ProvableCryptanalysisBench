| episode | status | certified bound (Lean) | log2 bound / log2 LB at λ=128 | at λ=256 | session | proof check |
|---|---|---|---|---|---|---|
| reference_setup_smoke | accepted | {"a": {"op": "order"}, "b": {"op": "constant", "value": 1}, "op": "add"} | - | - | - | 2.3 min |
| sonnet_proof_s3 | accepted | {"a": {"a": {"op": "constant", "value": 2}, "b": {"op": "sqrtOrder"}, "op": "mul"}, "b": {"op": "constant", "value": 4}, "op": "add"} | 64.9 / 63.8 | 129.0 / 127.9 | 30.0 min | 63 s |
| sonnet_proof_s4 | accepted | {"a": {"a": {"op": "constant", "value": 2}, "b": {"op": "sqrtOrder"}, "op": "mul"}, "b": {"op": "constant", "value": 5}, "op": "add"} | 64.9 / 63.8 | 129.0 / 127.9 | 36.8 min | 65 s |
| sonnet_proof_s5 | accepted | {"a": {"a": {"op": "constant", "value": 2}, "b": {"op": "sqrtOrder"}, "op": "mul"}, "b": {"op": "constant", "value": 3}, "op": "add"} | 64.9 / 63.8 | 129.0 / 127.9 | 34.1 min | 67 s |
