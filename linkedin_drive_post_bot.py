#!/usr/bin/env python3
"""Backward-compatible shim. Prefer: python run.py linkedin drive"""
from bots.linkedin.drive_post_bot import main

if __name__ == "__main__":
    raise SystemExit(main())
