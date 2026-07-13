#!/usr/bin/env python3
"""Weekly task-hours report for Founderp projects (exclude Investment Circle)."""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from attendance_bot import (
    DEFAULT_EMAIL,
    NAV_TIMEOUT_MS,
    STATE_FILE,
    do_login,
    is_logged_in,
    log,
    wait_for_page_ready,
)

EXCLUDE_PROJECT = "Investment Circle"
WEEKLY_TARGET = 40.0
OUT = Path("hours_probe")
OUT.mkdir(exist_ok=True)

# Minimal Bikram Sambat converter (AD <-> BS) for Nepal reporting.
# Algorithm adapted from common open BS calendars (valid ~1975–2100 AD).
_BS_MONTH_DAYS = [
    [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],  # 2000 BS placeholder index unused
]


def _load_bs_map():
    """Return list of 12 month lengths for BS years 1970–2090 approx via nepali calendar table.

    Uses a compact embedded table for fiscal-relevant years 2080–2083 BS
    (roughly 2023–2027 AD) plus neighbors.
    """
    # year -> 12 month lengths (Baishakh..Chaitra)
    return {
        2079: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2080: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30],
        2081: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        2082: [31, 31, 32, 31, 31, 30, 30, 30, 29, 30, 29, 31],
        2083: [31, 31, 32, 31, 31, 30, 30, 30, 29, 30, 29, 31],
        2084: [31, 32, 31, 32, 30, 31, 30, 29, 30, 29, 30, 30],
        2085: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
    }


# Reference: 2082-01-01 BS = 2025-04-14 AD (Baishakh 1)
_REF_BS = (2082, 1, 1)
_REF_AD = date(2025, 4, 14)


def bs_to_ad(y: int, m: int, d: int) -> date:
    table = _load_bs_map()
    if y not in table:
        raise ValueError(f"BS year {y} not in conversion table")
    days = 0
    # from REF_BS to target
    cy, cm, cd = _REF_BS
    target = (y, m, d)
    # walk forward/backward day by day is slow but fine for report; better: accumulate months
    # Convert both to day ordinals within known range
    def ordinal(yy, mm, dd):
        o = 0
        for year in range(min(table), yy):
            o += sum(table[year])
        o += sum(table[yy][: mm - 1])
        o += dd - 1
        return o

    delta = ordinal(y, m, d) - ordinal(*_REF_BS)
    return _REF_AD + timedelta(days=delta)


def ad_to_bs(ad: date) -> tuple[int, int, int]:
    table = _load_bs_map()
    delta = (ad - _REF_AD).days
    # walk from REF_BS
    y, m, d = _REF_BS
    remaining = delta
    if remaining >= 0:
        while remaining > 0:
            dim = table[y][m - 1]
            if d + remaining <= dim:
                d += remaining
                remaining = 0
            else:
                remaining -= dim - d + 1
                d = 1
                m += 1
                if m > 12:
                    m = 1
                    y += 1
                    if y not in table:
                        raise ValueError(f"BS year {y} out of table")
    else:
        remaining = -remaining
        while remaining > 0:
            if d > remaining:
                d -= remaining
                remaining = 0
            else:
                remaining -= d
                m -= 1
                if m < 1:
                    m = 12
                    y -= 1
                    if y not in table:
                        raise ValueError(f"BS year {y} out of table")
                d = table[y][m - 1]
    return y, m, d


BS_MONTHS = [
    "Baishakh",
    "Jestha",
    "Ashadh",
    "Shrawan",
    "Bhadra",
    "Ashwin",
    "Kartik",
    "Mangsir",
    "Poush",
    "Magh",
    "Falgun",
    "Chaitra",
]


def fmt_bs(ad: date) -> str:
    try:
        y, m, d = ad_to_bs(ad)
        return f"{y}-{m:02d}-{d:02d} ({BS_MONTHS[m-1]} {d})"
    except Exception:
        return "—"


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())  # Monday


def parse_day(value) -> date | None:
    if not value:
        return None
    if isinstance(value, dict):
        # nepali date object — convert via table if possible
        try:
            return bs_to_ad(int(value["year"]), int(value["month"]), int(value["day"]))
        except Exception:
            return None
    s = str(value)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        return None


def task_hours(task: dict) -> float:
    raw = task.get("estimatedHours")
    if raw not in (None, ""):
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    total = 0.0
    for sub in task.get("subtasks") or []:
        try:
            total += float(sub.get("estimatedTime") or 0)
        except (TypeError, ValueError):
            pass
    return total


def fetch_tasks(base: str, email: str, password: str) -> list[dict]:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            kwargs = {"ignore_https_errors": True}
            if STATE_FILE.exists():
                kwargs["storage_state"] = str(STATE_FILE)
            context = browser.new_context(**kwargs)
            page = context.new_page()
            page.goto(f"{base}/user/tasks", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            wait_for_page_ready(page)

            def session_ok() -> bool:
                if "/login" in page.url.lower():
                    return False
                # Tasks page or dashboard after auth — attendance markers are optional.
                if "/user" in page.url.lower():
                    return True
                return is_logged_in(page)

            if not session_ok():
                do_login(page, base, "/login", email, password)
                page.goto(f"{base}/user/tasks", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                wait_for_page_ready(page)
                if not session_ok():
                    log("error", "Still not authenticated after login.")
                    sys.exit(1)
            else:
                log("info", f"Session valid at {page.url}")

            # Prefer in-page fetch with cookies/session
            result = page.evaluate(
                """async () => {
                  const res = await fetch('/api/v1/user/tasks', { credentials: 'include' });
                  return await res.json();
                }"""
            )
            projects = page.evaluate(
                """async () => {
                  const res = await fetch('/api/v1/user/projects', { credentials: 'include' });
                  return await res.json();
                }"""
            )
            context.storage_state(path=str(STATE_FILE))
            (OUT / "tasks_live.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
            (OUT / "projects_live.json").write_text(json.dumps(projects, indent=2, default=str), encoding="utf-8")
            tasks = result.get("data") if isinstance(result, dict) else result
            return tasks or []
        finally:
            browser.close()


def main() -> int:
    email = os.environ.get("PORTAL_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("PORTAL_PASSWORD", email)
    base = os.environ.get("PORTAL_URL", "https://founderp.ai").rstrip("/")

    log("info", "Fetching tasks from Founderp...")
    tasks = fetch_tasks(base, email, password)
    log("info", f"Got {len(tasks)} tasks")

    # Exclude Investment Circle
    kept = []
    skipped = 0
    for t in tasks:
        pname = ((t.get("project") or {}).get("name") or "").strip()
        if pname.lower() == EXCLUDE_PROJECT.lower():
            skipped += 1
            continue
        kept.append(t)

    # Group by week of deadline (fallback startDate)
    by_week: dict[date, list] = defaultdict(list)
    for t in kept:
        d = parse_day(t.get("deadline")) or parse_day(t.get("startDate"))
        if not d:
            continue
        by_week[week_start(d)].append(t)

    if not by_week:
        print("No dated tasks found (excluding Investment Circle).")
        return 1

    first = min(by_week)
    last = max(by_week)
    # Include empty weeks from first through last (and current week)
    today_ws = week_start(date.today())
    end = max(last, today_ws)
    cursor = first
    rows = []
    cumulative = 0.0
    while cursor <= end:
        week_tasks = by_week.get(cursor, [])
        hours = sum(task_hours(t) for t in week_tasks)
        cumulative += hours
        sun = cursor + timedelta(days=6)
        gap = WEEKLY_TARGET - hours
        status = "OK" if hours >= WEEKLY_TARGET else ("EMPTY" if hours == 0 else "SHORT")
        # project breakdown
        proj_hours = defaultdict(float)
        for t in week_tasks:
            pname = ((t.get("project") or {}).get("name") or "?")
            proj_hours[pname] += task_hours(t)
        rows.append(
            {
                "week_start_ad": cursor.isoformat(),
                "week_end_ad": sun.isoformat(),
                "week_start_bs": fmt_bs(cursor),
                "week_end_bs": fmt_bs(sun),
                "hours": round(hours, 2),
                "target": WEEKLY_TARGET,
                "missing": round(max(0, gap), 2),
                "status": status,
                "cumulative": round(cumulative, 2),
                "task_count": len(week_tasks),
                "projects": dict(proj_hours),
                "titles": [t.get("title") for t in week_tasks],
            }
        )
        cursor += timedelta(days=7)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "employee": "Sandesh Bajracharya",
        "excluded_project": EXCLUDE_PROJECT,
        "weekly_target_hours": WEEKLY_TARGET,
        "tasks_total": len(tasks),
        "tasks_excluded_ic": skipped,
        "tasks_included": len(kept),
        "projects_included": sorted(
            {((t.get("project") or {}).get("name") or "?") for t in kept}
        ),
        "weeks": rows,
        "summary": {
            "weeks_total": len(rows),
            "weeks_ok": sum(1 for r in rows if r["status"] == "OK"),
            "weeks_short": sum(1 for r in rows if r["status"] == "SHORT"),
            "weeks_empty": sum(1 for r in rows if r["status"] == "EMPTY"),
            "hours_total": round(sum(r["hours"] for r in rows), 2),
            "hours_missing_total": round(sum(r["missing"] for r in rows), 2),
            "expected_if_all_40": round(len(rows) * WEEKLY_TARGET, 2),
        },
    }
    (OUT / "weekly_hours_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Markdown table
    lines = []
    lines.append("# Founderp weekly task-hours report")
    lines.append("")
    lines.append(f"- Generated: {report['generated_at']}")
    lines.append(f"- Excluded project: **{EXCLUDE_PROJECT}**")
    lines.append(f"- Included projects: {', '.join(report['projects_included'])}")
    lines.append(f"- Tasks included: {report['tasks_included']} (excluded IC: {skipped})")
    lines.append(f"- Weekly target: **{WEEKLY_TARGET:g} hours**")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    s = report["summary"]
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Weeks covered | {s['weeks_total']} |")
    lines.append(f"| Weeks >= 40h (OK) | {s['weeks_ok']} |")
    lines.append(f"| Weeks short (<40h) | {s['weeks_short']} |")
    lines.append(f"| Weeks empty (0h) | {s['weeks_empty']} |")
    lines.append(f"| Total hours (all weeks) | {s['hours_total']} |")
    lines.append(f"| Total missing vs 40h/wk | {s['hours_missing_total']} |")
    lines.append(f"| Expected if every week 40h | {s['expected_if_all_40']} |")
    lines.append("")
    lines.append("## Weekly breakdown (AD / BS)")
    lines.append("")
    lines.append("| Week (AD) | Week (BS) | Hours | Missing | Status | Cumulative | Tasks | Projects |")
    lines.append("|---|---|---:|---:|---|---:|---:|---|")
    for r in rows:
        projs = ", ".join(f"{k} {v:g}h" for k, v in r["projects"].items()) or "—"
        lines.append(
            f"| {r['week_start_ad']} → {r['week_end_ad']} | "
            f"{r['week_start_bs']} → {r['week_end_bs']} | "
            f"{r['hours']:g} | {r['missing']:g} | **{r['status']}** | {r['cumulative']:g} | "
            f"{r['task_count']} | {projs} |"
        )
    lines.append("")
    lines.append("## Weeks needing attention (SHORT / EMPTY)")
    lines.append("")
    bad = [r for r in rows if r["status"] != "OK"]
    if not bad:
        lines.append("None — all weeks meet the 40h target.")
    else:
        for r in bad:
            lines.append(
                f"- **{r['week_start_ad']} → {r['week_end_ad']}** "
                f"({r['week_start_bs']} → {r['week_end_bs']}): "
                f"{r['hours']:g}h / 40h — missing **{r['missing']:g}h** [{r['status']}]"
            )
            for title in r["titles"]:
                lines.append(f"  - {title}")
    lines.append("")

    md = "\n".join(lines)
    (OUT / "weekly_hours_report.md").write_text(md, encoding="utf-8")
    print(md)
    log("info", f"Wrote {OUT / 'weekly_hours_report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
