"""Repo root helpers for bots package."""

from __future__ import annotations

import sys
from pathlib import Path

# bots/lib/paths.py -> repo root is parents[2]
REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def repo_path(*parts: str) -> Path:
    return REPO_ROOT.joinpath(*parts)
