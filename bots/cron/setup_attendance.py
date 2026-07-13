#!/usr/bin/env python3
"""
Create cron-job.org schedules for daily clock-in / clock-out.

This script supports two cron dispatch routes:

1) Legacy `netlify` route (existing):
   cron-job.org -> Netlify function
   Netlify function -> Composio tool execution -> GitHub Actions

2) Current `composio-direct` route (preferred):
   cron-job.org -> Composio tool execution endpoint (POST)
   -> GitHub Actions workflow dispatch

In both cases, the cron schedule runs in the `ATTENDANCE_TZ` timezone (default: Asia/Kathmandu).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from bots.lib.attendance_dispatch import composio_client, load_dotenv

CRONJOB_API = "https://api.cron-job.org"
DEFAULT_TZ = "Asia/Kathmandu"
COMPOSIO_EXECUTE_URL = (
  "https://backend.composio.dev/api/v3.1/tools/execute/"
  "GITHUB_CREATE_A_WORKFLOW_DISPATCH_EVENT"
)


def parse_hhmm(text: str) -> tuple[int, int]:
  """
  Parse "HH:MM" into (hour, minute).
  """
  raw = (text or "").strip()
  if not raw:
    raise ValueError("time must be non-empty, expected HH:MM")
  hh, _, mm = raw.partition(":")
  hour = int(hh)
  minute = int(mm) if mm else 0
  if not (0 <= hour <= 23 and 0 <= minute <= 59):
    raise ValueError(f"invalid HH:MM: {text!r}")
  return hour, minute


def parse_force(value: str | None, *, default: bool = True) -> bool:
  if value is None:
    return default
  return value.strip().lower() not in {"0", "false", "no", "off"}


def build_composio_dispatch_body(
  *,
  action: str,
  force: bool,
  owner: str,
  repo: str,
  workflow_id: str,
  ref: str,
  composio_user_id: str | None,
) -> dict:
  """
  Body shape that matches `netlify/functions/attendance-cron.mjs`.
  """
  body = {
    "arguments": {
      "owner": owner,
      "repo": repo,
      "workflow_id": workflow_id,
      "ref": ref,
      "inputs": json.dumps({"action": action, "force": force}),
    },
    "dangerously_skip_version_check": True,
  }
  if composio_user_id:
    body["user_id"] = composio_user_id
  return body


def log(level: str, msg: str) -> None:
  from datetime import datetime

  stamp = datetime.now().strftime("%H:%M:%S")
  print(f"[{stamp}] {level.upper():7s} {msg}", flush=True)


def cronjob_request(method: str, path: str, api_key: str, payload: dict | None = None) -> dict:
  data = json.dumps(payload).encode() if payload is not None else None
  req = urllib.request.Request(
    f"{CRONJOB_API}{path}",
    data=data,
    method=method,
    headers={
      "Authorization": f"Bearer {api_key}",
      "Content-Type": "application/json",
    },
  )
  try:
    with urllib.request.urlopen(req, timeout=30) as resp:
      raw = resp.read().decode()
      return json.loads(raw) if raw else {}
  except urllib.error.HTTPError as exc:
    body = exc.read().decode(errors="replace")
    raise RuntimeError(f"cron-job.org {method} {path} -> {exc.code}: {body}") from exc


def list_jobs(api_key: str) -> list[dict]:
  data = cronjob_request("GET", "/jobs", api_key)
  return data.get("jobs") or []


def delete_job(api_key: str, job_id: int) -> None:
  cronjob_request("DELETE", f"/jobs/{job_id}", api_key)


def create_job(
  api_key: str,
  *,
  title: str,
  url: str,
  hour: int,
  minute: int,
  timezone: str,
  request_method: int = 0,
  headers: dict[str, str] | None = None,
  request_body: str | None = None,
) -> int:
  payload = {
    "job": {
      "title": title,
      "url": url,
      "enabled": True,
      "saveResponses": True,
      "requestMethod": request_method,
      # cron-job.org UI uses a list of Key/Value header rows.
      # If cron-job.org expects a different key name, we can adjust after a dry run.
      **({"headers": [{"key": k, "value": v} for k, v in headers.items()]} if headers else {}),
      **({"requestBody": request_body} if request_body else {}),
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
  data = cronjob_request("PUT", "/jobs", api_key, payload)
  job_id = data.get("jobId")
  if not job_id:
    raise RuntimeError(f"create job failed: {data}")
  return int(job_id)


def trigger_url(base: str, action: str, secret: str) -> str:
  sep = "&" if "?" in base else "?"
  return f"{base}{sep}action={action}&token={secret}"


def main() -> int:
  load_dotenv()
  parser = argparse.ArgumentParser(description="Create cron-job.org attendance schedules.")
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--replace", action="store_true", help="Delete existing attendance cron jobs first.")
  parser.add_argument("--skip-composio-test", action="store_true", help="Skip Composio client connectivity check.")
  parser.add_argument(
    "--mode",
    choices=["netlify", "composio-direct"],
    default=os.environ.get("CRON_DISPATCH_MODE", "composio-direct"),
    help="Dispatch route to use.",
  )
  parser.add_argument("--clock-in", default=os.environ.get("CLOCK_IN_TIME", "09:00"), help="HH:MM Nepal local time.")
  parser.add_argument(
    "--clock-out",
    default=os.environ.get("CLOCK_OUT_TIME", "18:45"),
    help="HH:MM Nepal local time.",
  )
  parser.add_argument(
    "--force",
    default=os.environ.get("ATTENDANCE_FORCE", "true"),
    help="Set workflow input force=true/false (default: true).",
  )
  args = parser.parse_args()

  api_key = os.environ.get("CRONJOB_API_KEY", "").strip()
  tz = os.environ.get("ATTENDANCE_TZ", DEFAULT_TZ)
  force = parse_force(args.force, default=True)

  clock_in_h, clock_in_m = parse_hhmm(args.clock_in)
  clock_out_h, clock_out_m = parse_hhmm(args.clock_out)

  base_url = os.environ.get("CRON_TRIGGER_URL", "").strip().rstrip("/")
  secret = os.environ.get("CRON_TRIGGER_SECRET", "").strip()
  if args.mode == "netlify":
    if not base_url or not secret:
      log("error", "Netlify mode: set CRON_TRIGGER_URL and CRON_TRIGGER_SECRET in .env")
      return 1

  # Only enforce required credentials when we are actually creating jobs.
  if not args.dry_run and not api_key:
    log("error", "CRONJOB_API_KEY missing. Create one at https://console.cron-job.org/settings")
    return 1

  if not args.skip_composio_test and os.environ.get("COMPOSIO_API_KEY"):
    log("info", "Testing Composio dispatch (dry clock-in)...")
    try:
      client = composio_client()
      # Don't actually dispatch in dry-run of whole script; user can test separately
      log("info", "Composio client OK.")
    except Exception as exc:  # noqa: BLE001
      log("warn", f"Composio check failed: {exc}")

  jobs_spec = [
    ("Attendance Clock In 9:00", "clock-in", clock_in_h, clock_in_m),
    ("Attendance Clock Out", "clock-out", clock_out_h, clock_out_m),
  ]

  if args.dry_run:
    for title, action, h, m in jobs_spec:
      if args.mode == "netlify":
        url = trigger_url(base_url, action, secret)
        extra = ""
      else:
        url = COMPOSIO_EXECUTE_URL
        extra = f" (x-api-key: COMPOSIO_API_KEY, body.inputs.action={action}, force={force})"
      log(
        "info",
        f"Would create: {title} @ {h:02d}:{m:02d} {tz} -> {url}{extra}",
      )
    return 0

  existing = list_jobs(api_key)
  if args.replace:
    for job in existing:
      title = job.get("title") or ""
      if title.startswith("Attendance Clock"):
        jid = job.get("jobId")
        if jid:
          log("info", f"Deleting old job {jid}: {title}")
          delete_job(api_key, int(jid))

  github_owner = os.environ.get("GITHUB_OWNER", "ssandesb")
  github_repo = os.environ.get("GITHUB_REPO", "clocked")
  github_workflow = os.environ.get("GITHUB_WORKFLOW", "attendance.yml")
  github_ref = os.environ.get("GITHUB_REF", "main")

  composio_user_id = os.environ.get("COMPOSIO_USER_ID") or None
  composio_project_api_key = os.environ.get("COMPOSIO_API_KEY", "").strip()

  for title, action, hour, minute in jobs_spec:
    if args.mode == "netlify":
      url = trigger_url(base_url, action, secret)
      job_id = create_job(
        api_key,
        title=title,
        url=url,
        hour=hour,
        minute=minute,
        timezone=tz,
        request_method=0,
      )
    else:
      if not composio_project_api_key:
        log("error", "composio-direct mode requires COMPOSIO_API_KEY (project api key for x-api-key header).")
        return 1
      url = COMPOSIO_EXECUTE_URL
      inputs_body = build_composio_dispatch_body(
        action=action,
        force=force,
        owner=github_owner,
        repo=github_repo,
        workflow_id=github_workflow,
        ref=github_ref,
        composio_user_id=composio_user_id,
      )
      request_body = json.dumps(inputs_body)
      headers = {
        "Content-Type": "application/json",
        "x-api-key": composio_project_api_key,
      }
      job_id = create_job(
        api_key,
        title=title,
        url=url,
        hour=hour,
        minute=minute,
        timezone=tz,
        request_method=1,
        headers=headers,
        request_body=request_body,
      )

    log("info", f"Created job {job_id}: {title} @ {hour:02d}:{minute:02d} {tz}")

  log(
    "info",
    f"Done. Jobs run 24/7 on cron-job.org using mode={args.mode} -> GitHub -> attendance_bot.py",
  )
  return 0


if __name__ == "__main__":
  try:
    sys.exit(main())
  except Exception as exc:  # noqa: BLE001
    log("error", str(exc))
    sys.exit(1)
