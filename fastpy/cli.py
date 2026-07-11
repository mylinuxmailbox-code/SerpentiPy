import argparse
import sys

from fastpy.native import compile_light, run_light, compile_heavy, exec_heavy
from fastpy.version import VERSION


def main():
    parser = argparse.ArgumentParser(
        prog="spyp",
        description="SerpentiPy - .spyp runner. Default: fast cached bytecode exec. --heavy: AOT native compile.",
    )
    parser.add_argument("--version", action="version", version=f"SerpentiPy {VERSION}")
    parser.add_argument(
        "--heavy", action="store_true",
        help="Full Nuitka standalone AOT compile to native binary (slow first run, cached, fastest execution)",
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
        exec_heavy(binary, args.args)
    else:
        code = compile_light(args.file)
        sys.exit(run_light(code, args.file))


if __name__ == "__main__":
    main()
