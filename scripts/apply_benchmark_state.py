#!/usr/bin/env python3
"""Apply the Section 5 transactions through the API, without the check table."""
import sys

from run_benchmark import apply_benchmark_state


if __name__ == "__main__":
    sys.exit(0 if apply_benchmark_state() else 1)
