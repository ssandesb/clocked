#!/usr/bin/env python3
"""Fill one Founderp task via UI and capture the real POST payload."""

from __future__ import annotations

from bots.lib.paths import REPO_ROOT

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from bots.lib.founderp_session import (
    DEFAULT_EMAIL,
    NAV_TIMEOUT_MS,
    STATE_FILE,
    do_login,
    log,
    wait_for_page_ready,
)
from bots.tasks.bulk_create import create_task

OUT = REPO_ROOT / "hours_probe"
OUT.mkdir(exist_ok=True)

base = os.environ.get("PORTAL_URL", "https://founderp.ai").rstrip("/")
email = os.environ.get("PORTAL_EMAIL", DEFAULT_EMAIL)
password = os.environ.get("PORTAL_PASSWORD", email)

captured: list[dict] = []


def main() -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        kwargs = {"ignore_https_errors": True, "viewport": {"width": 1400, "height": 1600}}
        if STATE_FILE.exists():
            kwargs["storage_state"] = str(STATE_FILE)
        context = browser.new_context(**kwargs)
        page = context.new_page()

        def on_request(req):
            if req.method in ("POST", "PUT", "PATCH") and "task" in req.url.lower():
                captured.append(
                    {
                        "url": req.url,
                        "method": req.method,
                        "headers": dict(req.headers),
                        "post_data": req.post_data,
                    }
                )
                log("info", f"CAPTURED {req.method} {req.url}")

        def on_response(res):
            if res.request.method in ("POST", "PUT", "PATCH") and "task" in res.url.lower():
                try:
                    body = res.text()
                except Exception:
                    body = ""
                captured.append({"url": res.url, "status": res.status, "response": body[:2000]})
                log("info", f"RESP {res.status} {res.url}")

        page.on("request", on_request)
        page.on("response", on_response)

        page.goto(f"{base}/user/tasks/add", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        wait_for_page_ready(page)
        if "/login" in page.url.lower() or page.get_by_role("button", name="Sign In", exact=False).count():
            do_login(page, base, "/login", email, password)
            page.goto(f"{base}/user/tasks/add", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            wait_for_page_ready(page)

        # Use current Nepali month day via bot helpers — dry_run=False for one tiny task
        task = {
            "title": "API CAPTURE probe task (delete me)",
            "description": "Temporary probe to capture create payload",
            "project": "Bhumi Finder",
            "company": "Clock b Business Technology",
            "assignee": "Sandesh Bajracharya",
            "priority": "Medium",
            "start_day": "first",
            "deadline_day": "last",
            "criteria": ["Probe only"],
            "subtasks": [{"title": "Probe hour", "hours": 1}],
        }
        defaults = {
            "company": "Clock b Business Technology",
            "project": "Bhumi Finder",
            "assignee": "Sandesh Bajracharya",
            "priority": "Medium",
            "deadline_day": "last",
        }
        ok = create_task(page, base, task, defaults, dry_run=False)
        log("info", f"create_task returned {ok}")
        (OUT / "ui_create_capture.json").write_text(json.dumps(captured, indent=2), encoding="utf-8")
        context.storage_state(path=str(STATE_FILE))
        browser.close()
        print(json.dumps(captured, indent=2)[:4000])
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
