#!/usr/bin/env python3
"""Backward-compatible shim. Prefer: python run.py linkedin prompt"""
from bots.linkedin.prompt_bot import main

if __name__ == "__main__":
    raise SystemExit(main())
