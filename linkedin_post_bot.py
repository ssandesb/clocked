#!/usr/bin/env python3
"""Backward-compatible shim. Prefer: python run.py linkedin post"""
from bots.linkedin.post_bot import main

if __name__ == "__main__":
    raise SystemExit(main())
