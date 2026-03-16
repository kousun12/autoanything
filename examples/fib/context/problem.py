"""
Fibonacci performance optimization.

The task is to make fib(n) as fast as possible while remaining correct.
The scoring function validates correctness against known values, then
benchmarks fib(36) and returns the median wall-clock time in seconds.

Known Fibonacci values (0-indexed):
    fib(0)  = 0
    fib(1)  = 1
    fib(10) = 55
    fib(20) = 6765
    fib(30) = 832040
    fib(36) = 14930352

Rules:
    - fib(n) must return the correct value for any non-negative integer n
    - No hardcoding return values — the function must compute them
    - No reading from the scoring directory
    - The function signature must remain: def fib(n) -> int
"""

BENCHMARK_N = 36
EXPECTED_FIB_36 = 14930352

CORRECTNESS_CASES = [
    (0, 0),
    (1, 1),
    (2, 1),
    (5, 5),
    (10, 55),
    (20, 6765),
    (30, 832040),
    (36, 14930352),
]
