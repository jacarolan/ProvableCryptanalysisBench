"""Rebuild trusted semantics and check a Submission.certificate in a fresh directory.

This is a cooperative-agent proof harness, not an OS security sandbox. Lean tactics
can execute code; run hostile submissions under a separate OS/container sandbox.
Acceptance requires kernel typechecking AND a transitive axiom allowlist.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
CORE_FILES = ("GGM/Model.lean", "GGM/Certificate.lean", "GGM/Export.lean")


def strip_comments_strings(text: str) -> str:
    """Preserve token boundaries and newlines, including nested Lean block comments."""
    out, i, depth = [], 0, 0
    while i < len(text):
        if depth:
            if text.startswith("/-", i):
                depth += 1
                i += 2
            elif text.startswith("-/", i):
                depth -= 1
                i += 2
            else:
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
        elif text.startswith("/-", i):
            depth = 1
            out.append(" ")
            i += 2
        elif text.startswith("--", i):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            out.append(" ")
        elif text[i] == '"':
            out.append(" ")
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                elif text[i] == '"':
                    i += 1
                    break
                else:
                    i += 1
        else:
            out.append(text[i])
            i += 1
    if depth:
        raise ValueError("Unterminated comment")
    return "".join(out)


def source_policy(source: str) -> None:
    if len(source.encode("utf-8")) > 2_000_000:
        raise ValueError("Submission exceeds 2 MB")
    clean = strip_comments_strings(source)
    imports = re.findall(r"(?m)^\s*import\s+([^\n]+)", clean)
    if imports != ["GGM.Certificate"]:
        raise ValueError("The only permitted import is: import GGM.Certificate")
    forbidden = r"\b(sorry|admit|axiom|unsafe|partial|opaque|noncomputable|native_decide|initialize|builtin_initialize|run_cmd|run_tac|run_elab|run_meta|elab|elab_rules|macro|macro_rules|syntax|notation|set_option|attribute|prelude)\b|#|@\["
    hit = re.search(forbidden, clean)
    if hit:
        raise ValueError(f"Unsupported submission construct: {hit.group()}")
    if "«" in clean or "»" in clean:
        raise ValueError("Quoted identifiers are not supported")


def dependency_paths(lean_root: Path) -> list[Path]:
    packages = lean_root / ".lake" / "packages"
    return [p / ".lake" / "build" / "lib" / "lean" for p in sorted(packages.iterdir())
            if p.is_dir() and (p / ".lake" / "build" / "lib" / "lean").is_dir()]


def lean_executable(lean_root: Path) -> str:
    override = os.environ.get("GGM_LEAN")
    if override:
        return override
    pinned = (lean_root / "lean-toolchain").read_text().strip()
    home = Path(os.environ.get("ELAN_HOME", str(Path.home() / ".elan")))
    folder = pinned.replace("/", "--").replace(":", "---")
    installed = home / "toolchains" / folder / "bin" / ("lean.exe" if os.name == "nt" else "lean")
    if installed.is_file():
        return str(installed)
    found = shutil.which("lean")
    if not found:
        raise RuntimeError("Lean not found. Install the toolchain in lean/lean-toolchain.")
    return found


def run_process(args: list[str], cwd: Path, env: dict, timeout: int) -> dict:
    start = time.monotonic()
    with tempfile.TemporaryFile() as stream:
        proc = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=stream, stderr=subprocess.STDOUT)
        try:
            proc.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            else:
                proc.kill()
            proc.wait()
        stream.seek(0)
        output = stream.read(2_000_000).decode("utf-8", errors="replace")
    return {"exit_code": proc.returncode, "timed_out": timed_out,
            "wall_secs": time.monotonic() - start, "output": output}


def parse_axioms(output: str) -> list[str]:
    if re.search(r"'Submission\.certificate' does not depend on any axioms", output):
        return []
    match = re.search(r"'Submission\.certificate' depends on axioms:\s*\[([^\]]*)\]", output)
    if not match:
        raise ValueError("Missing transitive axiom audit")
    axioms = [a.strip() for a in match.group(1).split(",") if a.strip()]
    unexpected = set(axioms) - ALLOWED_AXIOMS
    if unexpected:
        raise ValueError(f"Untrusted axioms: {sorted(unexpected)}")
    return axioms


@contextmanager
def core_lock(path: Path, timeout: int):
    """Serialize first builds for concurrent subagents. Never steal a live/stale lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Trusted-core build lock held: {path}. Check whether its process is still running.")
            time.sleep(0.25)
    try:
        yield
    finally:
        path.unlink()


def build_core(lean_root: Path, lean: str, env: dict, deps: list[Path], rec: dict, timeout: int) -> Path:
    """Cache only operator-owned modules, keyed by source/toolchain/manifest hashes.
    Submissions and their compiled objects are never reused between checks.
    """
    signature = json.dumps({"core": rec["core_sha256"], "manifest": rec["manifest_sha256"],
                            "lean": rec["lean_version"], "kernel_trust_level": 0}, sort_keys=True)
    digest = hashlib.sha256(signature.encode()).hexdigest()
    cache = lean_root.parent / ".cache" / "trusted" / digest
    with core_lock(cache.with_suffix(".lock"), timeout * len(CORE_FILES)):
        return build_core_locked(cache, lean_root, lean, env, deps, rec, timeout)


def build_core_locked(cache: Path, lean_root: Path, lean: str, env: dict,
                      deps: list[Path], rec: dict, timeout: int) -> Path:
    marker = cache / "compiled.json"
    if marker.is_file():
        hashes = json.loads(marker.read_text())
        expected_files = {str(Path(f).with_suffix(".olean")) for f in CORE_FILES}
        if set(hashes) == expected_files and all(
                (cache / f).is_file() and hashlib.sha256((cache / f).read_bytes()).hexdigest() == h
                for f, h in hashes.items()):
            rec["core_cache_hit"] = True
            return cache
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "GGM").mkdir(exist_ok=True)
    core_env = dict(env, LEAN_PATH=os.pathsep.join(map(str, [cache, *deps])))
    hashes = {}
    for f in CORE_FILES:
        shutil.copyfile(lean_root / f, cache / f)
        if hashlib.sha256((cache / f).read_bytes()).hexdigest() != rec["core_sha256"][f]:
            raise ValueError("Trusted sources changed during checking; retry with a stable snapshot")
        out = str(Path(f).with_suffix(".olean"))
        step = run_process([lean, "-DwarningAsError=true", "-DmaxHeartbeats=2000000", "-t0",
                            "-o", out, f], cache, core_env, timeout)
        step["file"] = f
        rec["steps"].append(step)
        if step["exit_code"] or step["timed_out"]:
            raise ValueError(f"Trusted module failed: {f}; see step output")
        hashes[out] = hashlib.sha256((cache / out).read_bytes()).hexdigest()
    temp_marker = marker.with_suffix(".tmp")
    temp_marker.write_text(json.dumps(hashes), encoding="utf-8")
    temp_marker.replace(marker)
    rec["core_cache_hit"] = False
    return cache


def check(source_path: Path, lean_root: Path | None = None, timeout: int = 300) -> dict:
    lean_root = (lean_root or ROOT / "lean").resolve()
    rec = {"schema_version": 1, "status": "rejected", "source_sha256": None,
           "problem": "uniform-prime-order-ggm-dlog", "steps": [], "certificate": None,
           "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           "kernel_trust_level": 0, "allowed_axioms": sorted(ALLOWED_AXIOMS),
           "cost_model": "unit-group-operations-plus-one-final-submission"}
    started = time.monotonic()
    try:
        if source_path.stat().st_size > 2_000_000:
            raise ValueError("Submission exceeds 2 MB")
        source = source_path.read_text(encoding="utf-8")
        rec["source_sha256"] = hashlib.sha256(source.encode()).hexdigest()
        source_policy(source)
        deps = dependency_paths(lean_root)
        if not deps:
            raise RuntimeError("Mathlib cache missing. In lean/, run: lake exe cache get")
        lean = lean_executable(lean_root)
        env = {k: v for k, v in os.environ.items() if not re.search("KEY|TOKEN|SECRET|PASSWORD", k, re.I)}
        version = run_process([lean, "--version"], lean_root, env, 30)
        expected_version = (lean_root / "lean-toolchain").read_text().strip().split(":v")[-1]
        if version["exit_code"] or f"version {expected_version}," not in version["output"]:
            raise RuntimeError("Wrong Lean version: " + version["output"])
        rec["lean_version"] = version["output"].strip()
        rec["core_sha256"] = {f: hashlib.sha256((lean_root / f).read_bytes()).hexdigest() for f in CORE_FILES}
        rec["manifest_sha256"] = hashlib.sha256((lean_root / "lake-manifest.json").read_bytes()).hexdigest()
        core = build_core(lean_root, lean, env, deps, rec, timeout)
        with tempfile.TemporaryDirectory(prefix="ggm-proof-check-") as temp:
            stage = Path(temp)
            env["LEAN_PATH"] = os.pathsep.join(map(str, [stage, core, *deps]))
            (stage / "Submission.lean").write_text(source, encoding="utf-8")
            (stage / "Audit.lean").write_text(
                "import Submission\nimport GGM.Export\n"
                "example : GGM.Certificate := Submission.certificate\n"
                "#print axioms Submission.certificate\n"
                "#eval IO.println (\"GGM_CERT_JSON=\" ++ GGM.exportCertificate Submission.certificate)\n",
                encoding="utf-8")
            for name in ["Submission.lean", "Audit.lean"]:
                args = [lean, "-DwarningAsError=true", "-DmaxHeartbeats=2000000", "-t0"]
                if name != "Audit.lean":
                    args += ["-o", str(Path(name).with_suffix(".olean"))]
                step = run_process(args + [name], stage, env, timeout)
                step["file"] = name
                rec["steps"].append(step)
                if step["exit_code"] or step["timed_out"]:
                    raise ValueError(f"Lean rejected {name}; see step output")
            output = rec["steps"][-1]["output"]
            rec["axioms"] = parse_axioms(output)
            matches = re.findall(r"(?m)^GGM_CERT_JSON=(.+)$", output)
            if len(matches) != 1:
                raise ValueError("Missing or ambiguous bound export")
            rec["certificate"] = json.loads(matches[0])
            if rec["certificate"]["seeds"] < 1:
                raise ValueError("Invalid seed count")
            rec["status"] = "accepted"
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
    rec["verification_wall_secs"] = time.monotonic() - started
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("submission", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--lean-root", type=Path)
    a = ap.parse_args()
    record = check(a.submission, a.lean_root, a.timeout)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k != "steps"}, indent=2))
    raise SystemExit(0 if record["status"] == "accepted" else 1)


if __name__ == "__main__":
    main()
