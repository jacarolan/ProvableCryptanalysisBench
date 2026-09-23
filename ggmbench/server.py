"""HTTP challenger. Launched as a subprocess; the secret config arrives on stdin (never on disk or
in argv), and the chosen port is printed as `PORT <n>` on stdout.

stdin JSON: {"rung": int, "level": int, "seed": hex, "admin_token": str,
            "budget": int (optional), "budget_factor": int (optional, budget = factor * Q*_UB)}

Agent-facing endpoints
  GET  /instance                          public parameters, labels, budget, queries used
  POST /query   {"ops": [[op, ...], ...]}  -> {"results": [...], "queries_used", "queries_remaining"}
  POST /submit  {"x": int|str}            -> {"correct": bool, ...}   (costs 1 query)
Harness-only (X-Admin-Token header)
  GET  /admin/result                      secret, planted structure, certified bounds, query log
  POST /admin/shutdown
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .instances import generate
from .oracle import BadLabel, BudgetExceeded, GroupOracle


def make_handler(oracle: GroupOracle, inst, admin_token: str, server_ref: list):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n) or b"{}")

        def _admin(self):
            return self.headers.get("X-Admin-Token") == admin_token

        def do_GET(self):
            if self.path == "/instance":
                return self._send(200, oracle.instance())
            if self.path == "/admin/result" and self._admin():
                return self._send(200, {
                    "rung": inst.rung, "level": inst.level, "N": str(inst.N), "x": str(inst.x),
                    "secret_structure": inst.secret_structure, "q_ub": inst.q_ub, "q_lb": inst.q_lb,
                    "naive_cost": str(inst.naive_cost), "budget": oracle.budget, "meta": inst.meta,
                    "public": oracle.instance(), **oracle.result()})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            try:
                body = self._body()
            except Exception:
                return self._send(400, {"error": "invalid JSON body"})
            if self.path == "/query":
                try:
                    res = oracle.query(body.get("ops"))
                except BudgetExceeded as e:
                    return self._send(429, {"error": str(e), "queries_used": oracle.queries_used,
                                            "queries_remaining": oracle.budget - oracle.queries_used})
                except BadLabel as e:
                    return self._send(400, {"error": f"unknown or malformed label: {str(e)[:80]}"})
                except (ValueError, TypeError) as e:
                    return self._send(400, {"error": str(e)[:300]})
                return self._send(200, {"results": res, "queries_used": oracle.queries_used,
                                        "queries_remaining": oracle.budget - oracle.queries_used})
            if self.path == "/submit":
                try:
                    ok = oracle.submit(int(body.get("x")))
                except BudgetExceeded as e:
                    return self._send(429, {"error": str(e)})
                except (ValueError, TypeError):
                    return self._send(400, {"error": "x must be an integer"})
                return self._send(200, {"correct": ok, "queries_used": oracle.queries_used,
                                        "queries_remaining": oracle.budget - oracle.queries_used})
            if self.path == "/admin/shutdown" and self._admin():
                self._send(200, {"ok": True})
                threading.Thread(target=server_ref[0].shutdown, daemon=True).start()
                return
            self._send(404, {"error": "not found"})

    return H


def main():
    cfg = json.loads(sys.stdin.readline())
    inst = generate(cfg["rung"], cfg["level"], bytes.fromhex(cfg["seed"]))
    budget = cfg.get("budget") or (cfg["budget_factor"] * inst.q_ub if cfg.get("budget_factor") else inst.budget)
    oracle = GroupOracle(inst.N, inst.x, inst.published, budget, inst.public_info())
    ref: list = []
    srv = ThreadingHTTPServer(("127.0.0.1", cfg.get("port", 0)), make_handler(oracle, inst, cfg["admin_token"], ref))
    ref.append(srv)
    print(f"PORT {srv.server_address[1]}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
