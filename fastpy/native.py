"""
Two-tier execution:

DEFAULT (spyp file.spyp): compile() to a code object, marshal-cache it,
exec() in-process. Near-zero compile cost (~ms), execution speed identical
to plain CPython — skips re-parsing on repeat runs, no false speed claim.

--heavy (spyp --heavy file.spyp): full Nuitka --standalone AOT compile to a
native binary, cached, exec'd via os.execv (process image replacement, not
subprocess) to remove launcher overhead. Slow first run, real speedup after.

Cache is namespaced by mode so switching --heavy on/off can't serve a stale
or wrong-typed artifact for the same source hash.
"""
import hashlib
import marshal
import os
import shutil
import subprocess
import sys
from pathlib import Path

CACHE_ROOT = Path(".fastpy_cache")


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


def _check_toolchain():
    missing = []
    try:
        import nuitka  # noqa: F401
    except ImportError:
        missing.append("nuitka (pip install nuitka)")
    if not (shutil.which("gcc") or shutil.which("clang")):
        missing.append("a C compiler (apt install gcc, or clang)")
    if missing:
        print("❌ SerpentiPy --heavy requires:")
        for m in missing:
            print(f"   - {m}")
        raise SystemExit(1)


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

    _check_toolchain()
    cache_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--lto=yes",
        "--python-flag=no_asserts",
        "--python-flag=no_docstrings",
        f"--output-dir={cache_dir}",
        "--remove-output",
        filename,
    ]

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
