#!/usr/bin/env python3
"""Backward-compatible shim. Prefer: python run.py tasks create ..."""
from bots.tasks.bulk_create import main

if __name__ == "__main__":
    raise SystemExit(main())
