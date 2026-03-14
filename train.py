"""Compatibility wrapper for the canonical state/train.py entrypoint."""

from runpy import run_module

if __name__ == "__main__":
    run_module("state.train", run_name="__main__")
