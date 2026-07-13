#!/usr/bin/env python3
"""Backward-compatible shim. Prefer: python run.py attendance ..."""
from bots.attendance.bot import main

if __name__ == "__main__":
    raise SystemExit(main())
