#!/usr/bin/env python3
"""
Create cron-job.org schedule: daily 11:50 PM -> Composio -> GitHub linkedin-post.yml.

Requires in .env:
  CRONJOB_API_KEY
  COMPOSIO_API_KEY
  COMPOSIO_USER_ID
  COMPOSIO_CONNECTED_ACCOUNT_ID   (GitHub connected account for dispatch tool)
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from attendance_dispatch import load_dotenv
from patch_cronjob_request import cronjob_request

COMPOSIO_EXECUTE_URL = (
  "https://backend.composio.dev/api/v3.1/tools/execute/"
  "GITHUB_CREATE_A_WORKFLOW_DISPATCH_EVENT"
)
DEFAULT_TZ = "Asia/Kathmandu"
JOB_TITLE = "Automate linkedin Post"


def log(msg: str) -> None:
  print(msg, flush=True)


def list_jobs(api_key: str) -> list[dict]:
  data = cronjob_request(api_key, "GET", "/jobs", {})
  return data.get("jobs") or []


def create_job(
  api_key: str,
  *,
  title: str,
  url: str,
  hour: int,
  minute: int,
  timezone: str,
  headers: dict[str, str],
  request_body: str,
) -> int:
  payload = {
    "job": {
      "title": title,
      "url": url,
      "enabled": True,
      "saveResponses": True,
      "requestMethod": 1,
      "headers": [{"key": k, "value": v} for k, v in headers.items()],
      "requestBody": request_body,
      "schedule": {
        "timezone": timezone,
        "expiresAt": 0,
        "hours": [hour],
        "minutes": [minute],
        "mdays": [-1],
        "months": [-1],
        "wdays": [-1],
      },
    }
  }
  data = cronjob_request(api_key, "PUT", "/jobs", payload)
  job_id = data.get("jobId")
  if not job_id:
    raise RuntimeError(f"create job failed: {data}")
  return int(job_id)


def build_dispatch_body(
  *,
  owner: str,
  repo: str,
  workflow_id: str,
  ref: str,
  user_id: str,
  connected_account_id: str,
) -> dict:
  return {
    "arguments": {
      "owner": owner,
      "repo": repo,
      "workflow_id": workflow_id,
      "ref": ref,
      "inputs": json.dumps({}),
    },
    "dangerously_skip_version_check": True,
    "user_id": user_id,
    "connected_account_id": connected_account_id,
  }


def main() -> int:
  load_dotenv()
  parser = argparse.ArgumentParser(description="Create LinkedIn post cron-job.org schedule.")
  parser.add_argument("--replace", action="store_true", help="Delete existing job with same title first.")
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--hour", type=int, default=int(os.environ.get("LINKEDIN_CRON_HOUR", "23")))
  parser.add_argument("--minute", type=int, default=int(os.environ.get("LINKEDIN_CRON_MINUTE", "50")))
  args = parser.parse_args()

  api_key = os.environ.get("CRONJOB_API_KEY", "").strip()
  composio_api_key = os.environ.get("COMPOSIO_API_KEY", "").strip()
  user_id = os.environ.get("COMPOSIO_USER_ID", "").strip()
  github_ca = os.environ.get("COMPOSIO_CONNECTED_ACCOUNT_ID", "").strip()
  tz = os.environ.get("ATTENDANCE_TZ", DEFAULT_TZ)

  owner = os.environ.get("GITHUB_OWNER", "ssandesb")
  repo = os.environ.get("GITHUB_REPO", "clocked")
  workflow_id = os.environ.get("LINKEDIN_WORKFLOW", "linkedin-post.yml")
  ref = os.environ.get("GITHUB_REF", "main")

  body = build_dispatch_body(
    owner=owner,
    repo=repo,
    workflow_id=workflow_id,
    ref=ref,
    user_id=user_id,
    connected_account_id=github_ca,
  )
  request_body = json.dumps(body)
  headers = {
    "Content-Type": "application/json",
    "x-api-key": composio_api_key,
  }

  if args.dry_run:
    log(f"Would create: {JOB_TITLE} @ {args.hour:02d}:{args.minute:02d} {tz}")
    log(f"URL: {COMPOSIO_EXECUTE_URL}")
    log(f"Body: {request_body}")
    return 0

  if not api_key:
    log("ERROR: CRONJOB_API_KEY missing")
    return 1
  if not composio_api_key or not user_id or not github_ca:
    log("ERROR: set COMPOSIO_API_KEY, COMPOSIO_USER_ID, COMPOSIO_CONNECTED_ACCOUNT_ID")
    return 1

  if args.replace:
    for job in list_jobs(api_key):
      if (job.get("title") or "").strip().lower() == JOB_TITLE.lower():
        jid = job.get("jobId")
        if jid:
          log(f"Deleting old job {jid}: {job.get('title')}")
          cronjob_request(api_key, "DELETE", f"/jobs/{jid}", {})

  job_id = create_job(
    api_key,
    title=JOB_TITLE,
    url=COMPOSIO_EXECUTE_URL,
    hour=args.hour,
    minute=args.minute,
    timezone=tz,
    headers=headers,
    request_body=request_body,
  )
  log(f"Created job {job_id}: {JOB_TITLE} @ {args.hour:02d}:{args.minute:02d} {tz}")
  return 0


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except Exception as exc:  # noqa: BLE001
    log(f"ERROR: {exc}")
    raise SystemExit(1) from exc
