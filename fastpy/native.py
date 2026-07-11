"""
Three-tier execution:

DEFAULT (spyp file.spyp): compile() to a code object, marshal-cache it,
exec() in-process. Near-zero compile cost, parity with plain CPython.

After PROMOTE_THRESHOLD interpreted runs of the same source hash, default
mode kicks off a --heavy Nuitka compile in a DETACHED background process
(start_new_session=True — survives spyp exiting) and still serves the fast
interpreted run immediately, so the triggering invocation pays zero extra
latency. Once the background compile finishes, subsequent default-mode runs
detect the ready binary and execv into it transparently — default becomes
--heavy speed after warmup, with no foreground wait ever.

--heavy (spyp --heavy file.spyp): explicit synchronous AOT compile, unchanged.

Ledger + lock file live next to the cache, keyed by source hash, so editing
the file resets both the run count and any stale promotion state.
"""
import hashlib
import json
import marshal
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

CACHE_ROOT = Path(".fastpy_cache")
PROMOTE_THRESHOLD = 3
LOCK_STALE_SECONDS = 300  # if a background compile lock is older than this, treat it as crashed/abandoned


def _hash_file(filename: str) -> str:
    return hashlib.sha256(Path(filename).read_bytes()).hexdigest()[:16]


def compile_light(filename: str):
    src_hash = _hash_file(filename)
    cache_file = CACHE_ROOT / f"{Path(filename).stem}.{src_hash}.pyc"

    if cache_file.exists():
        with open(cache_file, "rb") as f:
            return marshal.load(f)

    CACHE_ROOT.mkdir(exist_ok=True)
    source = Path(filename).read_text()
    code = compile(source, filename, "exec")

    with open(cache_file, "wb") as f:
        marshal.dump(code, f)

    return code


def run_light(code, filename: str) -> int:
    try:
        exec(code, {"__name__": "__main__", "__file__": filename})
        return 0
    except SystemExit as e:
        return e.code or 0
    except Exception as e:
        print("❌ SerpentiPy Error")
        print(e)
        return 1


def _check_toolchain(hard_fail: bool = True) -> bool:
    missing = []
    try:
        import nuitka  # noqa: F401
    except ImportError:
        missing.append("nuitka (pip install nuitka)")
    if not (shutil.which("gcc") or shutil.which("clang")):
        missing.append("a C compiler (apt install gcc, or clang)")
    if missing:
        if hard_fail:
            print("❌ SerpentiPy --heavy requires:")
            for m in missing:
                print(f"   - {m}")
            raise SystemExit(1)
        return False
    return True


def _binary_path(dist_dir: Path, filename: str) -> Path:
    base = Path(filename).name
    return dist_dir / f"{base}.dist" / f"{base}.bin"


def compile_heavy(filename: str) -> Path:
    src_hash = _hash_file(filename)
    stem = Path(filename).stem
    cache_dir = CACHE_ROOT / f"{stem}.{src_hash}.heavy"
    binary = _binary_path(cache_dir, filename)

    if binary.exists():
        return binary

    _check_toolchain(hard_fail=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    cmd = _nuitka_cmd(filename, cache_dir)
    print(f"⚙️  --heavy: compiling {filename} to native code (slow, cached after)...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("❌ Native compilation failed:")
        print(result.stderr[-2000:])
        raise SystemExit(1)

    if not binary.exists():
        print(f"❌ Compilation reported success but binary missing: {binary}")
        raise SystemExit(1)

    binary.chmod(0o755)
    return binary


def exec_heavy(binary: Path, extra_args=None):
    argv = [str(binary), *(extra_args or [])]
    os.execv(str(binary), argv)


def _nuitka_cmd(filename: str, cache_dir: Path):
    return [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--lto=yes",
        "--python-flag=no_asserts",
        "--python-flag=no_docstrings",
        f"--output-dir={cache_dir}",
        "--remove-output",
        filename,
    ]


# ---------- background auto-promotion ----------

def _ledger_path(src_hash: str) -> Path:
    return CACHE_ROOT / f".ledger.{src_hash}.json"


def _lock_path(src_hash: str) -> Path:
    return CACHE_ROOT / f".lock.{src_hash}"


def _read_ledger(src_hash: str) -> dict:
    path = _ledger_path(src_hash)
    if not path.exists():
        return {"runs": 0}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"runs": 0}


def _write_ledger(src_hash: str, data: dict):
    CACHE_ROOT.mkdir(exist_ok=True)
    _ledger_path(src_hash).write_text(json.dumps(data))


def _lock_is_stale(lock: Path) -> bool:
    try:
        return (time.time() - lock.stat().st_mtime) > LOCK_STALE_SECONDS
    except OSError:
        return True


def maybe_promote(filename: str, src_hash: str):
    """
    Called from the default (light) path after a successful interpreted run.
    Increments the run ledger; past PROMOTE_THRESHOLD, kicks off a detached
    background --heavy compile exactly once. Never blocks, never raises —
    any failure here must not affect the interpreted run that already
    completed successfully.
    """
    try:
        stem = Path(filename).stem
        heavy_dir = CACHE_ROOT / f"{stem}.{src_hash}.heavy"
        binary = _binary_path(heavy_dir, filename)
        if binary.exists():
            return  # already promoted, nothing to do

        lock = _lock_path(src_hash)
        if lock.exists() and not _lock_is_stale(lock):
            return  # compile already in flight from a previous run

        ledger = _read_ledger(src_hash)
        ledger["runs"] = ledger.get("runs", 0) + 1
        _write_ledger(src_hash, ledger)

        if ledger["runs"] < PROMOTE_THRESHOLD:
            return

        if not _check_toolchain(hard_fail=False):
            return  # silently stay on interpreted path forever for this file

        heavy_dir.mkdir(parents=True, exist_ok=True)
        lock.touch()

        cmd = _nuitka_cmd(filename, heavy_dir)
        # Detached: survives spyp exiting, does not block this run's exit.
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        # Promotion is best-effort. The interpreted run already succeeded;
        # never let background-compile plumbing surface an error to the user.
        pass


def try_promoted_binary(filename: str, src_hash: str):
    """Checked at the start of the default path, before falling back to
    interpret. Also cleans up a stale lock file if the binary is now ready."""
    stem = Path(filename).stem
    heavy_dir = CACHE_ROOT / f"{stem}.{src_hash}.heavy"
    binary = _binary_path(heavy_dir, filename)
    if binary.exists():
        _lock_path(src_hash).unlink(missing_ok=True)
        return binary
    return None
