"""Shared Founderp portal login / Playwright session helpers."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeout

from bots.lib.paths import REPO_ROOT

DEFAULT_EMAIL = "bajracharyasandeshh@gmail.com"
DEFAULT_LOGIN_PATH = "/login"
NAV_TIMEOUT_MS = 60_000
ACTION_TIMEOUT_MS = 30_000

STATE_FILE = Path(os.environ.get("STATE_FILE", str(REPO_ROOT / "state.json")))
DEBUG_SCREENSHOT = Path(os.environ.get("DEBUG_SCREENSHOT", str(REPO_ROOT / "debug-page.png")))


def log(level: str, msg: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {level.upper():7s} {msg}", flush=True)


def debug_page(page: Page, label: str) -> None:
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
    page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except PlaywrightTimeout:
        pass
    page.wait_for_timeout(1_500)


def first_visible(page: Page, selectors: list[str], timeout_ms: int = ACTION_TIMEOUT_MS) -> Locator:
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
    loc = first_visible(
        page,
        [
            'input[type="email"]',
            'input[name="email"]',
            'input[id="email"]',
            'input[autocomplete="email"]',
            'input[autocomplete="username"]',
            'input[placeholder*="email" i]',
            'input[placeholder*="mail" i]',
            'input[type="text"]',
        ],
    )
    loc.fill(email, timeout=ACTION_TIMEOUT_MS)


def fill_password(page: Page, password: str) -> None:
    loc = first_visible(
        page,
        [
            'input[type="password"]',
            'input[name="password"]',
            'input[id="password"]',
            'input[autocomplete="current-password"]',
            'input[placeholder*="password" i]',
        ],
    )
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
    try:
        page.get_by_role("button", name="Sign In", exact=False).wait_for(state="visible", timeout=2_000)
        return False
    except PlaywrightTimeout:
        return False


def session_ok_user_area(page: Page) -> bool:
    """True when authenticated on any /user page (not only attendance)."""
    if "/login" in page.url.lower():
        return False
    return "/user" in page.url.lower() or is_logged_in(page)


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
        log(
            "error",
            "Could not find the login form (email/password fields). "
            "Check PORTAL_URL / LOGIN_PATH secrets and inspect debug-page.png in workflow artifacts.",
        )
        sys.exit(1)

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


def get_bearer_token(page: Page) -> str | None:
    return page.evaluate(
        """() => {
          for (const k of Object.keys(localStorage)) {
            const v = localStorage.getItem(k) || '';
            if (v.startsWith('eyJ')) return v;
            try {
              const j = JSON.parse(v);
              const t = j && (j.token || j.accessToken || j.access_token);
              if (t) return t;
            } catch {}
          }
          for (const k of Object.keys(sessionStorage)) {
            const v = sessionStorage.getItem(k) || '';
            if (v.startsWith('eyJ')) return v;
          }
          return null;
        }"""
    )
