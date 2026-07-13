#!/usr/bin/env python3
"""Probe Founderp for projects/tasks hours (exclude Investment Circle)."""

from __future__ import annotations

from bots.lib.paths import REPO_ROOT

import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from bots.lib.founderp_session import (
    DEFAULT_EMAIL,
    NAV_TIMEOUT_MS,
    STATE_FILE,
    do_login,
    is_logged_in,
    log,
    wait_for_page_ready,
)

OUT = REPO_ROOT / "hours_probe"
OUT.mkdir(exist_ok=True)

CAPTURED: list[dict] = []


def on_response(response):
    try:
        url = response.url
        ct = (response.headers.get("content-type") or "").lower()
        if "json" not in ct:
            return
        if not any(
            k in url.lower()
            for k in ("project", "task", "hour", "work", "sprint", "report", "user/")
        ):
            # still capture api-ish paths
            if "/api/" not in url and "graphql" not in url.lower() and "supabase" not in url.lower():
                return
        body = response.json()
        CAPTURED.append({"url": url, "status": response.status, "body": body})
        print(f"[CAP] {response.status} {url[:160]}", flush=True)
    except Exception:
        pass


def main() -> int:
    email = os.environ.get("PORTAL_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("PORTAL_PASSWORD", email)
    base = os.environ.get("PORTAL_URL", "https://founderp.ai").rstrip("/")

    paths = [
        "/user/projects",
        "/user/tasks",
        "/user/dashboard",
        "/user/reports",
        "/user/my-projects",
        "/user/work-hours",
        "/user/timesheet",
    ]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            kwargs = {"ignore_https_errors": True}
            if STATE_FILE.exists():
                kwargs["storage_state"] = str(STATE_FILE)
            context = browser.new_context(**kwargs)
            page = context.new_page()
            page.on("response", on_response)

            page.goto(f"{base}/user/dashboard", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            wait_for_page_ready(page)
            if not is_logged_in(page):
                log("info", "Logging in...")
                do_login(page, base, "/login", email, password)
                page.goto(f"{base}/user/dashboard", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                wait_for_page_ready(page)
            else:
                log("info", "Session valid")

            context.storage_state(path=str(STATE_FILE))

            # Dump nav links
            links = page.evaluate(
                """() => Array.from(document.querySelectorAll('a'))
                    .map(a => ({href: a.getAttribute('href'), text: (a.innerText||'').trim().slice(0,80)}))
                    .filter(x => x.href && x.href.includes('/'))
                """
            )
            (OUT / "nav_links.json").write_text(json.dumps(links, indent=2), encoding="utf-8")
            log("info", f"Saved {len(links)} nav links")

            for path in paths:
                url = f"{base}{path}"
                log("info", f"Visiting {url}")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                    wait_for_page_ready(page)
                    safe = path.strip("/").replace("/", "_") or "root"
                    page.screenshot(path=str(OUT / f"{safe}.png"), full_page=True)
                    (OUT / f"{safe}.txt").write_text(page.inner_text("body")[:8000], encoding="utf-8")
                    log("info", f"  url now: {page.url}")
                except Exception as e:
                    log("warn", f"  failed {path}: {e}")

            # Also try clicking sidebar items that mention project/task
            for label in ("Projects", "My Projects", "Tasks", "Reports", "Timesheet", "Work Hours"):
                try:
                    loc = page.get_by_role("link", name=re.compile(label, re.I)).first
                    if loc.count() == 0:
                        loc = page.get_by_text(re.compile(f"^{label}$", re.I)).first
                    if loc.is_visible(timeout=1000):
                        loc.click()
                        wait_for_page_ready(page)
                        safe = label.lower().replace(" ", "_")
                        page.screenshot(path=str(OUT / f"click_{safe}.png"), full_page=True)
                        (OUT / f"click_{safe}.txt").write_text(page.inner_text("body")[:8000], encoding="utf-8")
                        log("info", f"Clicked {label} -> {page.url}")
                except Exception:
                    pass

            (OUT / "api_captures.json").write_text(
                json.dumps(CAPTURED, indent=2, default=str)[:2_000_000], encoding="utf-8"
            )
            log("info", f"Captured {len(CAPTURED)} JSON responses")
            context.storage_state(path=str(STATE_FILE))
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
