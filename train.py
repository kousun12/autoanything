"""
Backward-compatible entrypoint for the default challenge's mutable state.
"""

from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parent / "state" / "train.py"), run_name="__main__")
