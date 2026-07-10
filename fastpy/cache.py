import py_compile
from pathlib import Path

def compile_file(filename):
    cache_dir = Path(".fastpy_cache")
    cache_dir.mkdir(exist_ok=True)

    output = cache_dir / (Path(filename).stem + ".pyc")

    py_compile.compile(filename, cfile=str(output))

    return output

