import runpy
from pathlib import Path

def run_file(filename):
    path = Path(filename)

    if not path.exists():
        print(f"❌ File not found: {filename}")
        return

    try:
        runpy.run_path(str(path), run_name="__main__")
    except Exception as e:
        print("❌ SerpentiPy Error")
        print(e)

