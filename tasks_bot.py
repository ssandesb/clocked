#!/usr/bin/env python3
"""
Task creation bot — bulk-create tasks (with subtasks) on the Founderp portal.

Usage:
    python tasks_bot.py --file tasks.yaml            # create all tasks
    python tasks_bot.py --file tasks.yaml --dry-run  # fill forms, don't submit

See tasks.example.yaml for the input format.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

from attendance_bot import (
    ACTION_TIMEOUT_MS,
    DEFAULT_EMAIL,
    NAV_TIMEOUT_MS,
    do_login,
    log,
    wait_for_page_ready,
)

STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))
TASKS_ADD_PATH = "/user/tasks/add"

SECTIONS = [
    "Basic Task Information",
    "Assignment & Supervision",
    "Timeline & Scheduling",
    "Acceptance Criteria",
    "Subtasks",
]

POPUP = "[data-radix-popper-content-wrapper] button, [role='dialog'] button"


def expand_sections(page: Page) -> None:
    for name in SECTIONS:
        btn = page.get_by_role("button", name=name, exact=False).first
        try:
            if btn.get_attribute("aria-expanded") != "true":
                btn.click()
                page.wait_for_timeout(250)
        except PlaywrightTimeout:
            log("warn", f"Could not expand section: {name}")
    page.wait_for_timeout(400)


def select_combobox(page: Page, trigger_text: str, option: str) -> None:
    """Open a Radix combobox showing `trigger_text` and pick `option`."""
    page.get_by_role("combobox").filter(has_text=trigger_text).first.click()
    page.wait_for_timeout(400)
    select_option(page, option)


def select_option(page: Page, option: str) -> None:
    """Pick a dropdown option (handles labels like 'JS\\nJenish Sharma')."""
    candidates = [
        page.get_by_role("option", name=option, exact=True),
        page.get_by_role("option", name=option, exact=False),
        page.locator('[role="option"]').filter(has_text=option),
    ]
    for loc in candidates:
        try:
            loc.first.wait_for(state="visible", timeout=5_000)
            loc.first.click()
            page.wait_for_timeout(400)
            return
        except PlaywrightTimeout:
            continue
    raise PlaywrightTimeout(f'Could not select option "{option}"')


def enabled_days(page: Page) -> list[int]:
    days = page.evaluate(
        """() => {
            const pops = document.querySelectorAll('[data-radix-popper-content-wrapper], [role="dialog"]');
            const el = pops[pops.length - 1];
            if (!el) return [];
            return Array.from(el.querySelectorAll('.grid button')).map(b => ({
                day: b.innerText.trim(), disabled: b.disabled
            }));
        }"""
    )
    return [int(d["day"]) for d in days if not d["disabled"] and d["day"].isdigit()]


def pick_date(page: Page, trigger_name: str, want: int | str | None) -> None:
    """Open the Nepali date picker and choose a day.

    `want` may be a day number, "first"/"last" (enabled day), or None (skip).
    Falls back to the nearest enabled day if the requested one is disabled.
    """
    if want is None:
        return
    page.get_by_role("button", name=trigger_name).first.click()
    page.wait_for_timeout(700)
    days = enabled_days(page)
    if not days:
        log("warn", f"{trigger_name}: no enabled days in picker; skipping.")
        page.keyboard.press("Escape")
        return

    if want == "first":
        day = days[0]
    elif want == "last":
        day = days[-1]
    else:
        want = int(want)
        day = want if want in days else min(days, key=lambda d: abs(d - want))
        if day != want:
            log("warn", f"{trigger_name}: day {want} not selectable, using {day} "
                f"(enabled: {days[0]}-{days[-1]})")

    page.locator(POPUP).get_by_text(str(day), exact=True).first.click()
    page.wait_for_timeout(400)
    log("info", f"{trigger_name}: selected day {day}")


def first_empty_row_index(page: Page) -> int | None:
    titles = page.get_by_placeholder("Subtask title")
    for i in range(titles.count()):
        if not titles.nth(i).input_value().strip():
            return i
    return None


def fill_subtask_row(page: Page, sub: dict, default_assignee: str) -> None:
    idx = first_empty_row_index(page)
    if idx is None:
        page.get_by_role("button", name="Add Subtask", exact=False).first.click()
        page.wait_for_timeout(400)
        idx = first_empty_row_index(page)
        if idx is None:
            raise RuntimeError("Could not find an empty subtask row after Add Subtask")

    page.get_by_placeholder("Subtask title").nth(idx).fill(sub["title"])
    hours_box = page.get_by_placeholder("Time estimate").nth(idx)
    hours_box.fill(str(sub.get("hours", 1)))
    hours_box.press("Tab")  # commit the value so the total recalculates
    page.wait_for_timeout(200)

    # Row assignee: unset rows show "Select Assignee"; set explicitly when needed.
    row_box = page.get_by_role("combobox").filter(has_text="Select Assignee")
    want = sub.get("assignee", default_assignee)
    if row_box.count():
        row_box.first.click()
        page.wait_for_timeout(300)
        select_option(page, want)


def remove_empty_subtask_rows(page: Page) -> None:
    """Delete leftover blank rows the form auto-creates."""
    for _ in range(10):
        idx = first_empty_row_index(page)
        if idx is None:
            return
        row = page.get_by_placeholder("Subtask title").nth(idx).locator(
            "xpath=ancestor::div[.//button][1]"
        )
        x_btn = row.locator("button").last
        try:
            x_btn.click(timeout=2_000)
            page.wait_for_timeout(300)
        except PlaywrightTimeout:
            return


def create_task(page: Page, base_url: str, task: dict, defaults: dict, dry_run: bool) -> bool:
    title = task["title"]
    log("info", f"--- Creating task: {title!r}")

    page.goto(f"{base_url}{TASKS_ADD_PATH}", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    wait_for_page_ready(page)
    expand_sections(page)

    # Basic info
    page.get_by_placeholder("Short, clear title").fill(title)
    if desc := task.get("description"):
        page.get_by_placeholder("Detailed instructions, expectations, or context").fill(desc)

    company = task.get("company", defaults.get("company", "Clock b Business Technology"))
    select_combobox(page, "Select a company", company)
    page.wait_for_timeout(600)  # wait for assignee list to load

    if project := task.get("project", defaults.get("project")):
        select_combobox(page, "Select a Project", project)

    # Assignment
    assignee = task.get("assignee", defaults.get("assignee", "Sandesh Bajracharya"))
    select_combobox(page, "Select a user", assignee)

    priority = task.get("priority", defaults.get("priority"))
    if priority and priority.lower() != "medium":
        select_combobox(page, "Medium", priority.capitalize())

    # Timeline (Nepali calendar days)
    pick_date(page, "Select start date", task.get("start_day", defaults.get("start_day")))
    pick_date(page, "Select deadline", task.get("deadline_day", defaults.get("deadline_day", "last")))

    # Acceptance criteria (required)
    criteria = task.get("criteria") or ["Task completed as described"]
    for i, criterion in enumerate(criteria):
        name = "Add First Criteria" if i == 0 else "Add Criteria"
        page.get_by_role("button", name=name, exact=False).first.click()
        page.wait_for_timeout(300)
        page.get_by_placeholder("Enter acceptance criterion").nth(i).fill(criterion)

    # Subtasks (drive the auto-calculated Estimated Hours).
    # The form re-orders/auto-appends rows, so always fill the first EMPTY row
    # instead of trusting indexes.
    subtasks = task.get("subtasks") or [{"title": title, "hours": task.get("hours", 1)}]
    for sub in subtasks:
        if isinstance(sub, str):
            sub = {"title": sub}
        fill_subtask_row(page, sub, assignee)
    remove_empty_subtask_rows(page)

    est = page.get_by_placeholder("Calculated automatically").input_value()
    log("info", f"Form filled. Auto-estimated hours: {est or '?'}")

    if dry_run:
        page.screenshot(path=f"dryrun-{title[:30].replace(' ', '_')}.png", full_page=True)
        log("info", "Dry-run: NOT submitting.")
        return True

    page.get_by_role("button", name="Create Task", exact=True).click(timeout=ACTION_TIMEOUT_MS)
    log("info", 'Clicked "Create Task"')

    # Handle a possible confirmation dialog (same pattern as attendance clock-out).
    try:
        page.get_by_role("button", name="Confirm", exact=True).first.click(timeout=4_000)
        log("info", "Confirmation dialog: clicked Confirm.")
    except PlaywrightTimeout:
        pass

    # Success = navigated away from the add form, or a success toast appeared.
    try:
        page.wait_for_url(lambda u: TASKS_ADD_PATH not in u, timeout=15_000)
        log("info", f"Task created: {title!r} (redirected to {page.url})")
        return True
    except PlaywrightTimeout:
        pass
    for marker in ("success", "created", "submitted"):
        try:
            page.get_by_text(marker, exact=False).first.wait_for(state="visible", timeout=3_000)
            log("info", f"Task created: {title!r} (saw '{marker}' message)")
            return True
        except PlaywrightTimeout:
            continue
    page.screenshot(path=f"failed-{title[:30].replace(' ', '_')}.png", full_page=True)
    log("warn", f"Could not verify creation of {title!r} — check screenshot.")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Bulk-create tasks on the Founderp portal.")
    parser.add_argument("--file", required=True, help="YAML file with tasks (see tasks.example.yaml)")
    parser.add_argument("--dry-run", action="store_true", help="Fill forms but do not submit")
    parser.add_argument("--portal-url", default=None)
    args = parser.parse_args()

    base_url = (args.portal_url or os.environ.get("PORTAL_URL", "https://founderp.ai")).strip().rstrip("/")
    email = os.environ.get("PORTAL_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("PORTAL_PASSWORD", email)

    data = yaml.safe_load(Path(args.file).read_text(encoding="utf-8"))
    defaults = {k: v for k, v in data.items() if k != "tasks"}
    tasks = data.get("tasks", [])
    if not tasks:
        log("error", "No tasks found in input file.")
        return 1
    log("info", f"Loaded {len(tasks)} task(s) from {args.file}")

    ok = failed = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            kwargs: dict = {"ignore_https_errors": True, "viewport": {"width": 1400, "height": 1600}}
            if STATE_FILE.exists():
                kwargs["storage_state"] = str(STATE_FILE)
            context = browser.new_context(**kwargs)
            page = context.new_page()

            page.goto(f"{base_url}{TASKS_ADD_PATH}", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            wait_for_page_ready(page)
            if "/login" in page.url.lower():
                do_login(page, base_url, "/login", email, password)
                context.storage_state(path=str(STATE_FILE))

            for task in tasks:
                if isinstance(task, str):
                    task = {"title": task}
                try:
                    if create_task(page, base_url, task, defaults, args.dry_run):
                        ok += 1
                    else:
                        failed += 1
                except Exception as exc:
                    failed += 1
                    log("error", f"Task {task.get('title', '?')!r} failed: {exc}")
                    page.screenshot(path="task-error.png", full_page=True)

            context.storage_state(path=str(STATE_FILE))
        finally:
            browser.close()

    log("info", f"Done. Created: {ok}, failed: {failed}" + (" (dry-run)" if args.dry_run else ""))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
