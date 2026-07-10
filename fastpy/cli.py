import argparse

from fastpy.cache import compile_file
from fastpy.runner import run_file
from fastpy.version import VERSION


def main():
    parser = argparse.ArgumentParser(
        prog="spyp",
        description="SerpentiPy - fast .spyp script runner with bytecode caching",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"SerpentiPy {VERSION}",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Script file to compile and run (e.g. program.spyp)",
    )

    args = parser.parse_args()

    print(f"SerpentiPy {VERSION}")

    if not args.file:
        parser.print_help()
        raise SystemExit(1)

    compile_file(args.file)
    run_file(args.file)


if __name__ == "__main__":
    main()
