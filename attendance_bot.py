#!/usr/bin/env python3
"""
Automated Attendance Bot — clock-in / clock-out on a Founderp-style portal.
See README.md for configuration and GitHub Actions setup.
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
    Locator,
    Page,
    TimeoutError as PlaywrightTimeout,
    sync_playwright,
)

DEFAULT_EMAIL = "bajracharyasandeshh@gmail.com"
DEFAULT_TZ = "Asia/Kathmandu"
DEFAULT_CLOCK_IN = "09:00"
DEFAULT_CLOCK_OUT = "18:00"
DEFAULT_TOLERANCE_MIN = 90
DEFAULT_LOGIN_PATH = "/login"
DEFAULT_ATTENDANCE_PATH = "/user/attendance"

STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))
DEBUG_SCREENSHOT = Path(os.environ.get("DEBUG_SCREENSHOT", "debug-page.png"))

NAV_TIMEOUT_MS = 60_000
ACTION_TIMEOUT_MS = 30_000


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
    now_min = now_local.hour * 60 + now_local.minute
    if abs(now_min - minutes_of_day(clock_in)) <= tolerance:
        return "clock-in"
    if abs(now_min - minutes_of_day(clock_out)) <= tolerance:
        return "clock-out"
    return None


def debug_page(page: Page, label: str) -> None:
    """Log page state and save a screenshot to help diagnose selector failures."""
    log("error", f"Debug ({label}): url={page.url!r} title={page.title()!r}")
    try:
        inputs = page.locator("input").count()
        buttons = page.locator("button").count()
        log("error", f"Debug: visible inputs={inputs}, buttons={buttons}")
    except Exception as exc:
        log("error", f"Debug: could not count elements: {exc}")
    try:
        page.screenshot(path=str(DEBUG_SCREENSHOT), full_page=True)
        log("error", f"Debug screenshot saved to {DEBUG_SCREENSHOT}")
    except Exception as exc:
        log("error", f"Debug: screenshot failed: {exc}")


def wait_for_page_ready(page: Page) -> None:
    """SPAs often render the login form after domcontentloaded."""
    page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except PlaywrightTimeout:
        pass  # long-polling sites may never reach networkidle
    page.wait_for_timeout(1_500)  # extra buffer for React hydration


def first_visible(page: Page, selectors: list[str], timeout_ms: int = ACTION_TIMEOUT_MS) -> Locator:
    """Return the first locator that becomes visible within the timeout."""
    deadline = timeout_ms
    per_try = max(3_000, timeout_ms // max(len(selectors), 1))
    last_err: Exception | None = None
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=per_try)
            return loc
        except PlaywrightTimeout as exc:
            last_err = exc
            deadline -= per_try
            if deadline <= 0:
                break
    # Label / placeholder fallbacks (common on production forms)
    for label in ("Email", "E-mail", "Username"):
        loc = page.get_by_label(label, exact=False)
        try:
            loc.wait_for(state="visible", timeout=3_000)
            return loc
        except PlaywrightTimeout:
            pass
    for placeholder in ("email", "Email", "username", "Username"):
        loc = page.get_by_placeholder(placeholder, exact=False)
        try:
            loc.wait_for(state="visible", timeout=3_000)
            return loc
        except PlaywrightTimeout:
            pass
    if last_err:
        raise last_err
    raise PlaywrightTimeout(f"No visible input matched: {selectors}")


def fill_email(page: Page, email: str) -> None:
    loc = first_visible(page, [
        'input[type="email"]',
        'input[name="email"]',
        'input[id="email"]',
        'input[autocomplete="email"]',
        'input[autocomplete="username"]',
        'input[placeholder*="email" i]',
        'input[placeholder*="mail" i]',
        'input[type="text"]',
    ])
    loc.fill(email, timeout=ACTION_TIMEOUT_MS)


def fill_password(page: Page, password: str) -> None:
    loc = first_visible(page, [
        'input[type="password"]',
        'input[name="password"]',
        'input[id="password"]',
        'input[autocomplete="current-password"]',
        'input[placeholder*="password" i]',
    ])
    loc.fill(password, timeout=ACTION_TIMEOUT_MS)


def click_sign_in(page: Page) -> None:
    for name in ("Sign In", "Sign in", "Login", "Log in", "Submit"):
        btn = page.get_by_role("button", name=name, exact=False)
        try:
            btn.first.wait_for(state="visible", timeout=4_000)
            btn.first.click(timeout=ACTION_TIMEOUT_MS)
            return
        except PlaywrightTimeout:
            continue
    page.locator('button[type="submit"], input[type="submit"]').first.click(timeout=ACTION_TIMEOUT_MS)


def is_logged_in(page: Page) -> bool:
    if "/login" in page.url.lower():
        return False
    markers = [
        "Attendance Module",
        "Today's Attendance",
        "Clock In/Out",
        "Clock In",
    ]
    for text in markers:
        try:
            page.get_by_text(text, exact=False).first.wait_for(state="visible", timeout=4_000)
            return True
        except PlaywrightTimeout:
            continue
    # login form still showing?
    try:
        page.get_by_role("button", name="Sign In", exact=False).wait_for(state="visible", timeout=2_000)
        return False
    except PlaywrightTimeout:
        return False


def do_login(page: Page, base_url: str, login_path: str, email: str, password: str) -> None:
    login_url = f"{base_url}{login_path}"
    log("info", f"Logging in at {login_url}")
    page.goto(login_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    wait_for_page_ready(page)

    try:
        fill_email(page, email)
        fill_password(page, password)
        click_sign_in(page)
    except PlaywrightTimeout:
        debug_page(page, "login-form-not-found")
        log("error", "Could not find the login form (email/password fields). "
            "Check PORTAL_URL / LOGIN_PATH secrets and inspect debug-page.png in workflow artifacts.")
        sys.exit(1)

    # Wait for redirect away from login or attendance markers.
    try:
        page.wait_for_url(lambda url: "/login" not in url.lower(), timeout=ACTION_TIMEOUT_MS)
    except PlaywrightTimeout:
        pass

    wait_for_page_ready(page)
    if not is_logged_in(page) and "/login" in page.url.lower():
        try:
            err = page.locator("text=/invalid|incorrect|wrong|failed/i").first.inner_text(timeout=3_000)
            log("error", f"Login rejected: {err}")
        except PlaywrightTimeout:
            debug_page(page, "login-failed")
            log("error", "Login did not succeed (still on login page).")
        sys.exit(1)
    log("info", "Login OK")


def perform_action(page: Page, action: str) -> bool:
    button_name = "Clock In" if action == "clock-in" else "Clock Out"
    button = page.get_by_role("button", name=button_name, exact=False)

    try:
        button.first.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeout:
        log("warn", f'"{button_name}" button not visible — already actioned or wrong page state. No-op.')
        debug_page(page, f"no-{action}-button")
        return False

    button.first.click(timeout=ACTION_TIMEOUT_MS)
    log("info", f'Clicked "{button_name}"')

    expected_next = "Clock Out" if action == "clock-in" else "Start New Session"
    try:
        page.get_by_role("button", name=expected_next, exact=False).first.wait_for(
            state="visible", timeout=10_000
        )
        log("info", f'Verified: "{expected_next}" now visible.')
    except PlaywrightTimeout:
        log("warn", f'Clicked "{button_name}" but could not verify follow-up UI state.')
    return True


def run(action: str, base_url: str, login_path: str, attendance_path: str, email: str, password: str) -> None:
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

            perform_action(page, action)
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
                log("warn", f"Outside time windows — nothing to do.")
                return 0
        action = resolved

    log("info", f"Action: {action}")
    run(action, base_url, login_path, attendance_path, email, password)
    return 0


if __name__ == "__main__":
    sys.exit(main())
