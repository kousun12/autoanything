"""Compatibility wrapper for the canonical context/prepare.py entrypoint."""

from runpy import run_module

if __name__ == "__main__":
    run_module("context.prepare", run_name="__main__")
