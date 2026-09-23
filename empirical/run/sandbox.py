"""Challenger subprocess management and the agent's command sandbox (Windows / Git Bash).

Isolation is process-level only: secrets live solely in the challenger's memory (config is
passed on stdin), the workspace is a fresh temp directory outside the repo, and the sandbox
environment carries no API keys. There is no container; agents are instructed to stay in their
workspace and their transcripts are kept for audit.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # empirical/ (contains ggm/)
AGENT_FILES = os.path.join(REPO, "ggm", "agent_files")
GIT_BASH = next((p for p in [r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash") or ""]
                 if p and os.path.exists(p)), None)
WS_ROOT = os.path.join(tempfile.gettempdir(), "ggm_dl_ws")


class Challenger:
    def __init__(self, lam: int, seed: bytes | None = None):
        self.seed = seed or secrets.token_bytes(16)
        self.token = secrets.token_hex(16)
        cfg = {"lam": lam, "seed": self.seed.hex(), "admin_token": self.token}
        self.proc = subprocess.Popen([sys.executable, "-m", "ggm.server"], cwd=REPO,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.proc.stdin.write(json.dumps(cfg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline().strip()
        assert line.startswith("PORT "), line
        self.url = f"http://127.0.0.1:{int(line.split()[1])}"

    def _req(self, method, path):
        req = urllib.request.Request(self.url + path, method=method, data=b"{}" if method == "POST" else None,
                                     headers={"X-Admin-Token": self.token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    def public(self) -> dict:
        with urllib.request.urlopen(self.url + "/instance", timeout=60) as r:
            return json.loads(r.read())

    def result(self) -> dict:
        out = self._req("GET", "/admin/result")
        out["seed"] = self.seed.hex()
        return out

    def close(self):
        try:
            self._req("POST", "/admin/shutdown")
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def new_workspace(name: str) -> str:
    ws = os.path.join(WS_ROOT, name)
    if os.path.exists(ws):
        shutil.rmtree(ws, ignore_errors=True)
    os.makedirs(ws)
    shutil.copy(os.path.join(AGENT_FILES, "oracle_client.py"), ws)
    return ws


def sandbox_env(oracle_url: str) -> dict:
    pydir = os.path.dirname(sys.executable)
    git = os.path.dirname(os.path.dirname(GIT_BASH)) if GIT_BASH else ""
    path = os.pathsep.join([pydir, os.path.join(pydir, "Scripts"), os.path.join(git, "usr", "bin"),
                            os.path.join(git, "bin"), os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")])
    keep = {k: v for k, v in os.environ.items()
            if k.upper() in {"SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "COMSPEC",
                             "PATHEXT", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "APPDATA", "LOCALAPPDATA"}}
    return {**keep, "PATH": path, "ORACLE_URL": oracle_url, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def _kill_tree(pid: int):
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)


def run_command(cmd: str, cwd: str, env: dict, timeout: int = 600, max_chars: int = 16000) -> dict:
    """Run a bash command; stdout/stderr go to files so backgrounded children can't block us."""
    t0 = time.time()
    with tempfile.TemporaryFile() as out:
        proc = subprocess.Popen([GIT_BASH, "-c", cmd], cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL)
        try:
            proc.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            _kill_tree(proc.pid)
            timed_out = True
        out.seek(0)
        text = out.read().decode("utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[: max_chars * 2 // 3] + f"\n... [{len(text) - max_chars} chars truncated] ...\n" + text[-max_chars // 3:]
    return {"output": text, "exit_code": None if timed_out else proc.returncode, "timed_out": timed_out,
            "secs": round(time.time() - t0, 1)}
