"""
AOT compilation via Nuitka: .spyp source -> native binary, cached by source hash.

Cache layout: .fastpy_cache/<stem>.<hash>/<file>.dist/<file>.bin
First compile is slow (invokes gcc via Nuitka/Scons, ~15-90s depending on script).
Subsequent runs on unchanged source exec the cached binary directly — no
interpreter, no recompile. This is the only path that can legitimately beat
CPython on compute-bound code; bytecode caching alone cannot (see v1.0.x).
"""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

CACHE_ROOT = Path(".fastpy_cache")


def _hash_file(filename: str) -> str:
    return hashlib.sha256(Path(filename).read_bytes()).hexdigest()[:16]


def _check_toolchain():
    missing = []
    try:
        import nuitka  # noqa: F401
    except ImportError:
        missing.append("nuitka (pip install nuitka)")
    if not (shutil.which("gcc") or shutil.which("clang")):
        missing.append("a C compiler (apt install gcc, or clang)")
    if missing:
        print("❌ SerpentiPy native compilation requires:")
        for m in missing:
            print(f"   - {m}")
        raise SystemExit(1)


def _binary_path(dist_dir: Path, filename: str) -> Path:
    base = Path(filename).name
    return dist_dir / f"{base}.dist" / f"{base}.bin"


def compile_native(filename: str, fast: bool = False) -> Path:
    src_hash = _hash_file(filename)
    stem = Path(filename).stem
    cache_dir = CACHE_ROOT / f"{stem}.{src_hash}"
    binary = _binary_path(cache_dir, filename)

    if binary.exists():
        return binary

    _check_toolchain()
    cache_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        f"--output-dir={cache_dir}",
        "--remove-output",
    ]
    if fast:
        cmd += ["--lto=yes", "--python-flag=no_asserts", "--python-flag=no_docstrings"]
    cmd.append(filename)

    print(f"⚙️  Compiling {filename} to native code (first run, cached after)...")
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


def run_native(binary: Path, extra_args=None) -> int:
    result = subprocess.run([str(binary), *(extra_args or [])])
    return result.returncode
