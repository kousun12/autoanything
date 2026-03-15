"""Fibonacci implementation. Optimize this for speed."""


def fib(n):
    """Return the n-th Fibonacci number (0-indexed)."""
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
