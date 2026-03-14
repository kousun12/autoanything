"""
Backward-compatible entrypoint for the default challenge's read-only context.
"""

from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parent / "context" / "prepare.py"), run_name="__main__")
