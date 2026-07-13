#!/usr/bin/env python3
"""
Automated Attendance Bot — clock-in / clock-out on a Founderp-style portal.
See README.md / SCRIPTS.md for configuration and GitHub Actions setup.

Run:
  python run.py attendance clock-in --force
  python -m bots.attendance.bot --action auto
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from playwright.sync_api import Browser, Page, TimeoutError as PlaywrightTimeout, sync_playwright

from bots.lib.founderp_session import (
    ACTION_TIMEOUT_MS,
    DEFAULT_EMAIL,
    DEFAULT_LOGIN_PATH,
    NAV_TIMEOUT_MS,
    STATE_FILE,
    debug_page,
    do_login,
    is_logged_in,
    log,
    wait_for_page_ready,
)

DEFAULT_TZ = "Asia/Kathmandu"
DEFAULT_CLOCK_IN = "09:00"
DEFAULT_CLOCK_OUT = "18:00"
DEFAULT_TOLERANCE_MIN = 90
DEFAULT_ATTENDANCE_PATH = "/user/attendance"


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
    now_min = now_local.hour * 60 + now_local.minute
    if abs(now_min - minutes_of_day(clock_in)) <= tolerance:
        return "clock-in"
    if abs(now_min - minutes_of_day(clock_out)) <= tolerance:
        return "clock-out"
    return None


def detect_attendance_state(page: Page) -> str:
    """Read the attendance card UI to infer clock-in status."""
    try:
        if page.get_by_role("button", name="Clock Out", exact=False).first.is_visible(timeout=4_000):
            return "clocked-in"
    except PlaywrightTimeout:
        pass
    try:
        if page.get_by_role("button", name="Clock In", exact=False).first.is_visible(timeout=4_000):
            return "clocked-out"
    except PlaywrightTimeout:
        pass
    try:
        if page.get_by_role("button", name="Start New Session", exact=False).first.is_visible(timeout=2_000):
            return "clocked-out"
    except PlaywrightTimeout:
        pass
    try:
        if page.get_by_text("Attendance completed for today", exact=False).first.is_visible(timeout=2_000):
            return "clocked-out"
    except PlaywrightTimeout:
        pass
    return "unknown"


def resolve_action_for_state(requested: str, state: str, *, allow_toggle: bool) -> str | None:
    if state == "unknown":
        return requested

    if requested == "clock-in":
        if state == "clocked-out":
            return "clock-in"
        if state == "clocked-in":
            return "clock-out" if allow_toggle else None

    if requested == "clock-out":
        if state == "clocked-in":
            return "clock-out"
        if state == "clocked-out":
            return "clock-in" if allow_toggle else None

    return requested


def dismiss_confirmation_dialog(page: Page, action: str) -> None:
    heading = "Clock In Confirmation" if action == "clock-in" else "Clock Out Confirmation"
    try:
        page.get_by_text(heading, exact=False).first.wait_for(state="visible", timeout=5_000)
    except PlaywrightTimeout:
        pass

    confirm = page.get_by_role("button", name="Confirm", exact=True)
    try:
        confirm.first.wait_for(state="visible", timeout=5_000)
        confirm.first.click(timeout=ACTION_TIMEOUT_MS)
        log("info", f'Confirmation dialog: clicked "Confirm" for {action}.')
        page.wait_for_timeout(800)
    except PlaywrightTimeout:
        log("info", "No confirmation dialog (proceeded without extra click).")


def perform_action(page: Page, action: str) -> bool:
    button_name = "Clock In" if action == "clock-in" else "Clock Out"
    opposite = "Clock Out" if action == "clock-in" else "Clock In"

    target = page.get_by_role("button", name=button_name, exact=False)
    try:
        target.first.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeout:
        log("warn", f'"{button_name}" button not visible.')
        debug_page(page, f"no-{action}-button")
        return False

    target.first.click(timeout=ACTION_TIMEOUT_MS)
    log("info", f'Clicked "{button_name}"')

    dismiss_confirmation_dialog(page, action)

    expected = "clocked-in" if action == "clock-in" else "clocked-out"
    for _ in range(6):
        state = detect_attendance_state(page)
        if state == expected:
            log("info", f"Verified attendance state: {state}")
            return True
        page.wait_for_timeout(1_000)

    follow_ups = [opposite]
    if action == "clock-out":
        follow_ups.extend(["Start New Session", "Attendance completed for today"])
    for name in follow_ups:
        try:
            if name == "Attendance completed for today":
                page.get_by_text(name, exact=False).first.wait_for(state="visible", timeout=3_000)
            else:
                page.get_by_role("button", name=name, exact=False).first.wait_for(
                    state="visible", timeout=3_000
                )
            log("info", f'Verified: "{name}" now visible.')
            return True
        except PlaywrightTimeout:
            continue
    log("warn", f'Clicked "{button_name}" but could not verify follow-up UI state.')
    return True


def run(
    action: str,
    base_url: str,
    login_path: str,
    attendance_path: str,
    email: str,
    password: str,
    *,
    allow_toggle: bool,
) -> None:
    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch(headless=True)
        try:
            context_kwargs: dict = {"ignore_https_errors": True}
            if STATE_FILE.exists():
                context_kwargs["storage_state"] = str(STATE_FILE)
                log("info", f"Loaded saved session from {STATE_FILE}")

            context = browser.new_context(**context_kwargs)
            page = context.new_page()

            attendance_url = f"{base_url}{attendance_path}"
            page.goto(attendance_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            wait_for_page_ready(page)

            if is_logged_in(page):
                log("info", "Existing session still valid — skipping login.")
            else:
                log("info", "No valid session — performing fresh login.")
                do_login(page, base_url, login_path, email, password)
                page.goto(attendance_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                wait_for_page_ready(page)
                if not is_logged_in(page):
                    debug_page(page, "post-login-not-authenticated")
                    log("error", "Still not authenticated after login. Aborting.")
                    sys.exit(1)

            state = detect_attendance_state(page)
            log("info", f"Attendance state: {state}")
            effective = resolve_action_for_state(action, state, allow_toggle=allow_toggle)
            if effective is None:
                log("info", f"Requested {action} but already in that state — no-op.")
                context.storage_state(path=str(STATE_FILE))
                return
            if effective != action:
                log("info", f"Flipping action: {action} -> {effective} (currently {state})")
            perform_action(page, effective)
            context.storage_state(path=str(STATE_FILE))
            log("info", f"Session state saved to {STATE_FILE}")
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Automated attendance clock-in/out bot.")
    parser.add_argument("--action", choices=["clock-in", "clock-out", "auto"], default="auto")
    parser.add_argument("--portal-url", default=None, help="Override PORTAL_URL env var.")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    base_url = (args.portal_url or os.environ.get("PORTAL_URL", "")).strip().rstrip("/")
    if not base_url:
        log("error", "PORTAL_URL is not set.")
        return 1
    if not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"

    login_path = os.environ.get("LOGIN_PATH", DEFAULT_LOGIN_PATH)
    attendance_path = os.environ.get("ATTENDANCE_PATH", DEFAULT_ATTENDANCE_PATH)
    email = os.environ.get("PORTAL_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("PORTAL_PASSWORD", email)

    tz = ZoneInfo(os.environ.get("ATTENDANCE_TZ", DEFAULT_TZ))
    clock_in_t = parse_hhmm(os.environ.get("CLOCK_IN_TIME", DEFAULT_CLOCK_IN), "CLOCK_IN_TIME")
    clock_out_t = parse_hhmm(os.environ.get("CLOCK_OUT_TIME", DEFAULT_CLOCK_OUT), "CLOCK_OUT_TIME")
    tolerance = int(os.environ.get("TIME_TOLERANCE_MIN", DEFAULT_TOLERANCE_MIN))

    now_local = datetime.now(tz)
    log("info", f"Local time: {now_local:%Y-%m-%d %H:%M} ({tz.key}) | portal: {base_url}")

    if now_local.weekday() >= 5 and not args.force:
        log("warn", "Weekend — skipping (use --force to override).")
        return 0

    action = args.action
    if action == "auto":
        resolved = resolve_auto_action(now_local, clock_in_t, clock_out_t, tolerance)
        if resolved is None:
            if args.force:
                now_min = now_local.hour * 60 + now_local.minute
                mid = (minutes_of_day(clock_in_t) + minutes_of_day(clock_out_t)) / 2
                resolved = "clock-in" if now_min < mid else "clock-out"
                log("warn", f"--force resolved action to {resolved}.")
            else:
                log("warn", "Outside time windows — nothing to do.")
                return 0
        action = resolved

    log("info", f"Action: {action}")
    allow_toggle = args.force or os.environ.get("SMART_TOGGLE", "").lower() in ("1", "true", "yes")
    run(action, base_url, login_path, attendance_path, email, password, allow_toggle=allow_toggle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
