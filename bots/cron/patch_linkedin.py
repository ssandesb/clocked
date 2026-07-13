#!/usr/bin/env python3
"""Patch cron-job.org job 8043558 (LinkedIn post) with Composio auth + body."""

from __future__ import annotations

import json
import os

from bots.lib.attendance_dispatch import load_dotenv
from bots.cron.setup_linkedin import (
  JOB_TITLE,
  build_dispatch_body,
  patch_job_request,
)

DEFAULT_JOB_ID = 8043558


def main() -> int:
  load_dotenv()
  api_key = os.environ.get("CRONJOB_API_KEY", "").strip()
  composio_api_key = os.environ.get("COMPOSIO_API_KEY", "").strip()
  user_id = os.environ.get("COMPOSIO_USER_ID", "pg-test-8c570a15-d401-43f3-ab2a-aeb201de5b7b").strip()
  github_ca = os.environ.get("COMPOSIO_CONNECTED_ACCOUNT_ID", "ca_Mzv0hIhqWgB8").strip()
  job_id = int(os.environ.get("LINKEDIN_CRON_JOB_ID", DEFAULT_JOB_ID))

  if not api_key:
    raise RuntimeError("CRONJOB_API_KEY missing")
  if not composio_api_key:
    raise RuntimeError("COMPOSIO_API_KEY missing")

  body = build_dispatch_body(
    owner=os.environ.get("GITHUB_OWNER", "ssandesb"),
    repo=os.environ.get("GITHUB_REPO", "clocked"),
    workflow_id=os.environ.get("LINKEDIN_WORKFLOW", "linkedin-post.yml"),
    ref=os.environ.get("GITHUB_REF", "main"),
    user_id=user_id,
    connected_account_id=github_ca,
  )
  request_body = json.dumps(body)
  headers = {
    "Content-Type": "application/json",
    "x-api-key": composio_api_key,
  }

  patch_job_request(api_key, job_id, headers=headers, request_body=request_body)
  print(f"Patched job {job_id}: {JOB_TITLE}", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
