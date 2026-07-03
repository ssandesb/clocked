#!/usr/bin/env python3
"""
Automated Attendance Bot
========================

Automates clock-in / clock-out on a Founderp-style employment portal.

Flow (3 steps):
  1. Open  {PORTAL_URL}/login
  2. Fill email + password and sign in (skipped if a saved session is still valid)
  3. Open  {PORTAL_URL}/user/attendance  and click "Clock In" or "Clock Out"

Configuration is fully dynamic via environment variables (never hardcode secrets):

  PORTAL_URL          Base URL of the portal, e.g. https://founderp.com
  PORTAL_EMAIL        Login email    (default: bajracharyasandeshh@gmail.com)
  PORTAL_PASSWORD     Login password (default: same as PORTAL_EMAIL)
  ATTENDANCE_TZ       IANA timezone for shift times (default: Asia/Kathmandu)
  CLOCK_IN_TIME       Local clock-in time,  HH:MM (default: 09:00)
  CLOCK_OUT_TIME      Local clock-out time, HH:MM (default: 18:00)
  TIME_TOLERANCE_MIN  Window (minutes) around each time in which "auto" mode
                      matches that action (default: 90)

Usage:
  python attendance_bot.py --action auto
  python attendance_bot.py --action clock-in  --force
  python attendance_bot.py --action clock-out --portal-url https://founderp.com

Exit codes:
  0  success, or nothing to do (idempotent no-op)
  1  hard failure (login failed, page unreachable, etc.)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import (
    Browser,
    Page,
    TimeoutError as PlaywrightTimeout,
    sync_playwright,
)

DEFAULT_EMAIL = "bajracharyasandeshh@gmail.com"
DEFAULT_TZ = "Asia/Kathmandu"
DEFAULT_CLOCK_IN = "09:00"
DEFAULT_CLOCK_OUT = "18:00"
DEFAULT_TOLERANCE_MIN = 90
STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))

NAV_TIMEOUT_MS = 45_000
ACTION_TIMEOUT_MS = 15_000


def log(level: str, msg: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {level.upper():7s} {msg}", flush=True)


def parse_hhmm(raw: str, name: str) -> dtime:
    try:
        h, m = raw.strip().split(":")
        return dtime(int(h), int(m))
    except (ValueError, AttributeError):
        log("error", f"{name} must be HH:MM, got: {raw!r}")
        sys.exit(1)


def minutes_of_day(t: dtime) -> int:
    return t.hour * 60 + t.minute


def resolve_auto_action(now_local: datetime, clock_in: dtime, clock_out: dtime, tolerance: int) -> str | None:
    """Pick clock-in or clock-out when the current time is within the tolerance
    window of the configured slot. Returns None when neither window matches."""
    now_min = now_local.hour * 60 + now_local.minute
    if abs(now_min - minutes_of_day(clock_in)) <= tolerance:
        return "clock-in"
    if abs(now_min - minutes_of_day(clock_out)) <= tolerance:
        return "clock-out"
    return None


def is_logged_in(page: Page) -> bool:
    """True when the attendance page rendered without bouncing us to /login."""
    if "/login" in page.url:
        return False
    try:
        page.get_by_role("button", name="Sign In").wait_for(state="visible", timeout=2_000)
        return False  # login form is showing
    except PlaywrightTimeout:
        pass
    try:
        page.get_by_text("Attendance Module").wait_for(state="visible", timeout=5_000)
        return True
    except PlaywrightTimeout:
        return False


def do_login(page: Page, base_url: str, email: str, password: str) -> None:
    log("info", f"Logging in at {base_url}/login")
    page.goto(f"{base_url}/login", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    page.locator('input[type="email"]').fill(email, timeout=ACTION_TIMEOUT_MS)
    page.locator('input[type="password"]').fill(password, timeout=ACTION_TIMEOUT_MS)
    page.get_by_role("button", name="Sign In").click(timeout=ACTION_TIMEOUT_MS)

    # Successful login lands on the attendance page.
    try:
        page.get_by_text("Attendance Module").wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)
    except PlaywrightTimeout:
        # Surface the portal's own error message if there is one.
        try:
            err = page.get_by_text("Invalid email or password").inner_text(timeout=2_000)
            log("error", f"Login rejected: {err}")
        except PlaywrightTimeout:
            log("error", "Login did not reach the attendance page (unknown reason).")
        sys.exit(1)
    log("info", "Login OK")


def perform_action(page: Page, action: str) -> bool:
    """Click the Clock In / Clock Out button. Returns True if clicked,
    False for an idempotent no-op (button absent = already done)."""
    button_name = "Clock In" if action == "clock-in" else "Clock Out"
    button = page.get_by_role("button", name=button_name, exact=True)

    try:
        button.wait_for(state="visible", timeout=8_000)
    except PlaywrightTimeout:
        log("warn", f'"{button_name}" button not visible - already actioned or shift state mismatch. No-op.')
        return False

    button.click(timeout=ACTION_TIMEOUT_MS)
    log("info", f'Clicked "{button_name}"')

    # Verify the UI flipped state (Clock In -> Clock Out appears, and vice versa).
    expected_next = "Clock Out" if action == "clock-in" else "Start New Session"
    try:
        page.get_by_role("button", name=expected_next).wait_for(state="visible", timeout=8_000)
        log("info", f'Verified: "{expected_next}" now visible - {action} recorded.')
    except PlaywrightTimeout:
        log("warn", f'Clicked "{button_name}" but could not verify the follow-up state. Check the portal.')
    return True


def run(action: str, base_url: str, email: str, password: str) -> None:
    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch(headless=True)
        try:
            # Reuse a saved session when available; the portal invalidates
            # sessions daily/5-min so this often falls through to fresh login.
            context_kwargs = {}
            if STATE_FILE.exists():
                context_kwargs["storage_state"] = str(STATE_FILE)
                log("info", f"Loaded saved session state from {STATE_FILE}")

            context = browser.new_context(**context_kwargs)
            page = context.new_page()

            page.goto(f"{base_url}/user/attendance", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

            if is_logged_in(page):
                log("info", "Existing session still valid - skipping login.")
            else:
                log("info", "No valid session - performing fresh login.")
                do_login(page, base_url, email, password)
                page.goto(f"{base_url}/user/attendance", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                if not is_logged_in(page):
                    log("error", "Still not authenticated after login. Aborting.")
                    sys.exit(1)

            perform_action(page, action)

            # Persist cookies/localStorage so the next run can try session reuse.
            context.storage_state(path=str(STATE_FILE))
            log("info", f"Session state saved to {STATE_FILE}")
        finally:
            browser.close()  # always terminate browser threads cleanly


def main() -> int:
    parser = argparse.ArgumentParser(description="Automated attendance clock-in/out bot.")
    parser.add_argument(
        "--action",
        choices=["clock-in", "clock-out", "auto"],
        default="auto",
        help="Which action to run. 'auto' picks based on current local time vs configured slots.",
    )
    parser.add_argument("--portal-url", default=None, help="Override PORTAL_URL env var.")
    parser.add_argument("--force", action="store_true", help="Run even on weekends / outside time windows.")
    args = parser.parse_args()

    base_url = (args.portal_url or os.environ.get("PORTAL_URL", "")).strip().rstrip("/")
    if not base_url:
        log("error", "PORTAL_URL is not set (env var or --portal-url). e.g. https://founderp.com")
        return 1
    if not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"

    email = os.environ.get("PORTAL_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("PORTAL_PASSWORD", email)

    tz = ZoneInfo(os.environ.get("ATTENDANCE_TZ", DEFAULT_TZ))
    clock_in_t = parse_hhmm(os.environ.get("CLOCK_IN_TIME", DEFAULT_CLOCK_IN), "CLOCK_IN_TIME")
    clock_out_t = parse_hhmm(os.environ.get("CLOCK_OUT_TIME", DEFAULT_CLOCK_OUT), "CLOCK_OUT_TIME")
    tolerance = int(os.environ.get("TIME_TOLERANCE_MIN", DEFAULT_TOLERANCE_MIN))

    now_local = datetime.now(tz)
    log("info", f"Local time: {now_local:%Y-%m-%d %H:%M} ({tz.key}) | portal: {base_url}")

    if now_local.weekday() >= 5 and not args.force:  # Sat=5, Sun=6
        log("warn", "Weekend - skipping (use --force to override).")
        return 0

    action = args.action
    if action == "auto":
        resolved = resolve_auto_action(now_local, clock_in_t, clock_out_t, tolerance)
        if resolved is None:
            if args.force:
                # Forced auto outside both windows: pick by closest slot.
                now_min = now_local.hour * 60 + now_local.minute
                mid = (minutes_of_day(clock_in_t) + minutes_of_day(clock_out_t)) / 2
                resolved = "clock-in" if now_min < mid else "clock-out"
                log("warn", f"Outside both time windows; --force resolved action to {resolved}.")
            else:
                log("warn",
                    f"Not within +/-{tolerance} min of {clock_in_t:%H:%M} or {clock_out_t:%H:%M} - nothing to do.")
                return 0
        action = resolved

    log("info", f"Action: {action}")
    run(action, base_url, email, password)
    return 0


if __name__ == "__main__":
    sys.exit(main())
