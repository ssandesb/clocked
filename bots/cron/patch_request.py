#!/usr/bin/env python3
"""
Patch an existing cron-job.org job's saved request body.

This is used when the cron-job UI won't persist Advanced->Request body edits.
It keeps the existing schedule (e.g. every minute) and updates only the fields
needed for Composio -> GitHub workflow dispatch.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request

from bots.lib.attendance_dispatch import load_dotenv


CRONJOB_API_BASE = "https://api.cron-job.org"


def log(msg: str) -> None:
  print(msg, flush=True)


def cronjob_request(api_key: str, method: str, path: str, payload: dict) -> dict:
  data = json.dumps(payload).encode("utf-8")
  req = urllib.request.Request(
    f"{CRONJOB_API_BASE}{path}",
    data=data,
    method=method,
    headers={
      "Authorization": f"Bearer {api_key}",
      "Content-Type": "application/json",
    },
  )
  try:
    with urllib.request.urlopen(req, timeout=30) as resp:
      raw = resp.read().decode("utf-8", errors="replace")
      return json.loads(raw) if raw else {}
  except urllib.error.HTTPError as exc:
    body = exc.read().decode(errors="replace") if exc.fp else ""
    raise RuntimeError(f"cron-job.org {method} {path} -> {exc.code}: {body}") from exc


def build_composio_execute_payload(
  *,
  action: str,
  force: bool,
  owner: str,
  repo: str,
  workflow_id: str,
  ref: str,
  composio_user_id: str,
  connected_account_id: str,
) -> dict:
  # Composio requires arguments.inputs to be a JSON string.
  inputs_str = json.dumps({"action": action, "force": force})
  return {
    "arguments": {
      "owner": owner,
      "repo": repo,
      "workflow_id": workflow_id,
      "ref": ref,
      "inputs": inputs_str,
    },
    "dangerously_skip_version_check": True,
    "user_id": composio_user_id,
    "connected_account_id": connected_account_id,
  }


def main() -> int:
  load_dotenv()
  parser = argparse.ArgumentParser()
  parser.add_argument("--job-id", type=int, default=8040643)
  parser.add_argument("--action", choices=["clock-in", "clock-out"], default="clock-out")
  parser.add_argument("--force", default=os.environ.get("ATTENDANCE_FORCE", "true"))
  args = parser.parse_args()

  cronjob_api_key = os.environ.get("CRONJOB_API_KEY", "").strip()
  composio_project_api_key = os.environ.get("COMPOSIO_API_KEY", "").strip()
  composio_user_id = os.environ.get("COMPOSIO_USER_ID", "").strip()
  connected_account_id = os.environ.get("COMPOSIO_CONNECTED_ACCOUNT_ID", "").strip()

  if not cronjob_api_key:
    raise RuntimeError("CRONJOB_API_KEY missing in .env")
  if not composio_project_api_key:
    raise RuntimeError("COMPOSIO_API_KEY missing in .env (used as x-api-key header)")
  if not composio_user_id:
    raise RuntimeError("COMPOSIO_USER_ID missing in .env (your Composio connected-account entity id)")
  if not connected_account_id:
    raise RuntimeError(
      "COMPOSIO_CONNECTED_ACCOUNT_ID missing in .env "
      "(your connected account id e.g. ca_Mzv0hIhqWgB8)"
    )

  force_val = str(args.force).strip().lower() not in {"0", "false", "no", "off"}

  # Must match attendance_dispatch defaults / GitHub workflow location.
  owner = os.environ.get("GITHUB_OWNER", "ssandesb")
  repo = os.environ.get("GITHUB_REPO", "clocked")
  workflow_id = os.environ.get("GITHUB_WORKFLOW", "attendance.yml")
  ref = os.environ.get("GITHUB_REF", "main")

  composio_payload = build_composio_execute_payload(
    action=args.action,
    force=force_val,
    owner=owner,
    repo=repo,
    workflow_id=workflow_id,
    ref=ref,
    composio_user_id=composio_user_id,
    connected_account_id=connected_account_id,
  )

  request_body = json.dumps(composio_payload)

  delta_job = {
    "requestMethod": 1,  # POST
    "headers": [{"key": "x-api-key", "value": composio_project_api_key}],
    "requestBody": request_body,
  }

  resp = cronjob_request(
    api_key=cronjob_api_key,
    method="PATCH",
    path=f"/jobs/{args.job_id}",
    payload={"job": delta_job},
  )

  log(f"Patched cron-job jobId={args.job_id}. Response: {resp}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

