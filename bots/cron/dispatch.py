#!/usr/bin/env python3
"""Dispatch clock-in / clock-out via Composio -> GitHub Actions (runs attendance_bot.py)."""

from __future__ import annotations

import argparse
import json
import sys

from bots.lib.attendance_dispatch import composio_client, dispatch_attendance, load_dotenv


def log(level: str, msg: str) -> None:
  from datetime import datetime

  stamp = datetime.now().strftime("%H:%M:%S")
  print(f"[{stamp}] {level.upper():7s} {msg}", flush=True)


def main() -> int:
  load_dotenv()

  parser = argparse.ArgumentParser(description="Dispatch attendance via Composio + GitHub Actions.")
  parser.add_argument("--action", choices=["clock-in", "clock-out"], required=True)
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--no-force", action="store_true")
  args = parser.parse_args()

  user_id = __import__("os").environ.get("COMPOSIO_USER_ID") or None
  force = not args.no_force

  if args.dry_run:
    log("info", f"Dry run: would dispatch {args.action} (force={force})")
    return 0

  client = composio_client()
  result = dispatch_attendance(client, args.action, user_id=user_id, force=force)
  log("info", f"Dispatch OK: {json.dumps(result.get('data', result), default=str)[:500]}")
  owner = __import__("os").environ.get("GITHUB_OWNER", "ssandesb")
  repo = __import__("os").environ.get("GITHUB_REPO", "clocked")
  workflow = __import__("os").environ.get("GITHUB_WORKFLOW", "attendance.yml")
  log("info", f"Runs: https://github.com/{owner}/{repo}/actions/workflows/{workflow}")
  return 0


if __name__ == "__main__":
  try:
    sys.exit(main())
  except Exception as exc:  # noqa: BLE001
    log("error", str(exc))
    sys.exit(1)
