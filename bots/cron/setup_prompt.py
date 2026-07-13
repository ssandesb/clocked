#!/usr/bin/env python3
"""
Create or update cron-job.org schedule -> Composio -> linkedin-prompt-post.yml.

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

from bots.lib.composio_tools import load_dotenv
from bots.cron.patch_request import cronjob_request
from bots.cron.setup_linkedin import (
  COMPOSIO_EXECUTE_URL,
  DEFAULT_TZ,
  build_dispatch_body,
  create_job,
  list_jobs,
  patch_job_request,
)

JOB_TITLE = "Automate LinkedIn Post (Prompt-driven)"


def log(msg: str) -> None:
  print(msg, flush=True)


def patch_existing_job(
  api_key: str,
  job_id: int,
  *,
  headers: dict[str, str],
  request_body: str,
) -> None:
  patch_job_request(api_key, job_id, headers=headers, request_body=request_body)
  log(f"Patched existing job {job_id}: {JOB_TITLE}")


def main() -> int:
  load_dotenv()
  parser = argparse.ArgumentParser(description="Create/patch prompt-driven LinkedIn cron job.")
  parser.add_argument("--replace", action="store_true", help="Delete existing job with same title first.")
  parser.add_argument("--patch-only", action="store_true", help="Only PATCH job id (no create).")
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--hour", type=int, default=int(os.environ.get("LINKEDIN_CRON_HOUR", "14")))
  parser.add_argument("--minute", type=int, default=int(os.environ.get("LINKEDIN_CRON_MINUTE", "0")))
  parser.add_argument("--job-id", type=int, default=int(os.environ.get("LINKEDIN_CRON_JOB_ID", "8043558")))
  args = parser.parse_args()

  api_key = os.environ.get("CRONJOB_API_KEY", "").strip()
  composio_api_key = os.environ.get("COMPOSIO_API_KEY", "").strip()
  user_id = os.environ.get("COMPOSIO_USER_ID", "").strip()
  github_ca = os.environ.get("COMPOSIO_CONNECTED_ACCOUNT_ID", "").strip()
  tz = os.environ.get("SCHEDULE_TZ", os.environ.get("ATTENDANCE_TZ", DEFAULT_TZ))

  owner = os.environ.get("GITHUB_OWNER", "ssandesb")
  repo = os.environ.get("GITHUB_REPO", "clocked")
  workflow_id = os.environ.get("LINKEDIN_PROMPT_WORKFLOW", "linkedin-prompt-post.yml")
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
    log(f"Would configure: {JOB_TITLE} @ {args.hour:02d}:{args.minute:02d} {tz}")
    log(f"workflow_id: {workflow_id}")
    log(f"URL: {COMPOSIO_EXECUTE_URL}")
    log(f"Body: {request_body}")
    return 0

  if not api_key:
    log("ERROR: CRONJOB_API_KEY missing")
    return 1
  if not composio_api_key or not user_id or not github_ca:
    log("ERROR: set COMPOSIO_API_KEY, COMPOSIO_USER_ID, COMPOSIO_CONNECTED_ACCOUNT_ID")
    return 1

  if args.patch_only:
    patch_existing_job(api_key, args.job_id, headers=headers, request_body=request_body)
    return 0

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
  patch_job_request(api_key, job_id, headers=headers, request_body=request_body)
  log(f"Created job {job_id}: {JOB_TITLE} -> {workflow_id} @ {args.hour:02d}:{args.minute:02d} {tz}")
  return 0


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except Exception as exc:  # noqa: BLE001
    log(f"ERROR: {exc}")
    raise SystemExit(1) from exc
