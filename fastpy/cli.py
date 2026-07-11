import argparse
import sys

from fastpy.native import (
    compile_light, run_light,
    compile_heavy, exec_heavy,
    _hash_file, try_promoted_binary, maybe_promote,
)
from fastpy.version import VERSION


def main():
    parser = argparse.ArgumentParser(
        prog="spyp",
        description="SerpentiPy - .spyp runner. Default: cached exec, auto-promotes to native after repeat runs. --heavy: force AOT now.",
    )
    parser.add_argument("--version", action="version", version=f"SerpentiPy {VERSION}")
    parser.add_argument(
        "--heavy", action="store_true",
        help="Force full Nuitka standalone AOT compile now (slow first run, cached, fastest execution)",
    )
    parser.add_argument("file", nargs="?", help="Script file to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed through to the program")

    args = parser.parse_args()

    if not args.file:
        print(f"SerpentiPy {VERSION}")
        parser.print_help()
        raise SystemExit(1)

    if args.heavy:
        binary = compile_heavy(args.file)
        exec_heavy(binary, args.args)  # execv — never returns on success

    # Default path: has a background-promoted binary finished compiling
    # since a prior run? If so, this run gets native speed with zero wait.
    src_hash = _hash_file(args.file)
    promoted = try_promoted_binary(args.file, src_hash)
    if promoted:
        exec_heavy(promoted, args.args)  # never returns on success

    code = compile_light(args.file)
    exit_code = run_light(code, args.file)
    maybe_promote(args.file, src_hash)  # fire-and-forget, after the run, never blocks output
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
