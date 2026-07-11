import argparse
import sys

from fastpy.native import compile_native, run_native
from fastpy.version import VERSION


def main():
    parser = argparse.ArgumentParser(
        prog="spyp",
        description="SerpentiPy - AOT-compiled .spyp runner (Nuitka backend)",
    )
    parser.add_argument("--version", action="version", version=f"SerpentiPy {VERSION}")
    parser.add_argument(
        "--fast", action="store_true",
        help="Aggressive native optimization: LTO, strip asserts/docstrings",
    )
    parser.add_argument("file", nargs="?", help="Script file to compile (once) and run natively")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed through to the compiled program")

    args = parser.parse_args()
    print(f"SerpentiPy {VERSION}")

    if not args.file:
        parser.print_help()
        raise SystemExit(1)

    binary = compile_native(args.file, fast=args.fast)
    sys.exit(run_native(binary, args.args))


if __name__ == "__main__":
    main()
