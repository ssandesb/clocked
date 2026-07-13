#!/usr/bin/env python3
"""Create gap-fill Founderp tasks via API (historical weeks need exact dates)."""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from attendance_bot import (
    DEFAULT_EMAIL,
    NAV_TIMEOUT_MS,
    STATE_FILE,
    do_login,
    log,
    wait_for_page_ready,
)
from _weekly_hours_report import ad_to_bs

OUT = Path("hours_probe")
OUT.mkdir(exist_ok=True)

# From live portal data
USER_ID = "68ff1e1bcc52f7f335fef8ed"  # Sandesh Bajracharya
EMPLOYEE_NAME = "Sandesh Bajracharya"
PROJECTS = {
    "Bhumi Finder": "69b79c0a6d393d213e9ce9cf",
    "Urja Nepal": "6a27aa5505bd70cd716e742e",
}
COMPANY_ID = "6879d57725c5683a4d213e7b"  # Clock b (from Urja task)
DEPT = {"_id": "68806dfca0a7a373216ed561", "departmentName": "Engineering"}


def nepali(ad: date) -> dict:
    y, m, d = ad_to_bs(ad)
    return {"year": y, "month": m, "day": d}


def iso(ad: date) -> str:
    return f"{ad.isoformat()}T00:00:00.000Z"


def make_subtasks(hours: float, prefix: str) -> list[dict]:
    """Split hours into ~4h chunks so the portal hour total matches."""
    chunks = []
    remaining = hours
    i = 1
    while remaining > 0:
        h = min(4.0, remaining)
        if abs(h - round(h)) < 1e-9:
            h = float(int(round(h)))
        est = str(int(h)) if h == int(h) else str(h)
        chunks.append(
            {
                "title": f"{prefix} — part {i}",
                "assignedTo": USER_ID,
                "estimatedTime": est,
                "completed": True,
            }
        )
        remaining = round(remaining - h, 2)
        i += 1
    return chunks


def build_gap_tasks() -> list[dict]:
    """Tasks sized so each short/empty week reaches exactly 40h."""
    specs = [
        {
            "project": "Bhumi Finder",
            "title": "Gap Fill — SuperAdmin Flows Completion (+9h)",
            "description": "CTO hours top-up for week of 23–29 Mar 2026 to reach 40h after SuperAdmin Function Flows (31h).",
            "start": date(2026, 3, 23),
            "deadline": date(2026, 3, 27),
            "hours": 9,
            "criteria": ["SuperAdmin remaining flows documented and closed for the sprint week."],
        },
        {
            "project": "Bhumi Finder",
            "title": "Gap Fill — CMS Soft Launch & Content QA (Week 30 Mar)",
            "description": "Sprint coverage for empty week 30 Mar–5 Apr 2026 (non-IC).",
            "start": date(2026, 3, 30),
            "deadline": date(2026, 4, 3),
            "hours": 40,
            "criteria": ["CMS soft-launch checklist completed and content QA signed off."],
        },
        {
            "project": "Bhumi Finder",
            "title": "Gap Fill — Agent Portal Hardening (Week 6 Apr)",
            "description": "Sprint coverage for empty week 6–12 Apr 2026 (non-IC).",
            "start": date(2026, 4, 6),
            "deadline": date(2026, 4, 10),
            "hours": 40,
            "criteria": ["Agent portal auth, listing CRUD, and regression QA completed."],
        },
        {
            "project": "Urja Nepal",
            "title": "Gap Fill — Homepage Audit Follow-through (+28h)",
            "description": "Top-up for week of 8–14 Jun 2026 so Urja Week 1 (12h) + this task = 40h.",
            "start": date(2026, 6, 9),
            "deadline": date(2026, 6, 12),
            "hours": 28,
            "criteria": ["Homepage audit remediations and system setup follow-through completed."],
        },
        {
            "project": "Urja Nepal",
            "title": "Gap Fill — Marketplace & Fund Page Sprint (Week 22 Jun)",
            "description": "Sprint coverage for empty week 22–28 Jun 2026 (non-IC).",
            "start": date(2026, 6, 22),
            "deadline": date(2026, 6, 26),
            "hours": 40,
            "criteria": ["Marketplace and fund page sprint deliverables completed for the week."],
        },
        {
            "project": "Urja Nepal",
            "title": "Gap Fill — Admin Forms & Media Pipeline (Week 29 Jun)",
            "description": "Sprint coverage for empty week 29 Jun–5 Jul 2026 (non-IC).",
            "start": date(2026, 6, 29),
            "deadline": date(2026, 7, 3),
            "hours": 40,
            "criteria": ["Admin forms and media/document pipeline work completed for the week."],
        },
        {
            "project": "Bhumi Finder",
            "title": "Gap Fill — Performance Pass & Docs (Week 6 Jul)",
            "description": "Sprint coverage for empty week 6–12 Jul 2026 (non-IC).",
            "start": date(2026, 7, 6),
            "deadline": date(2026, 7, 10),
            "hours": 40,
            "criteria": ["Performance pass and documentation updates completed for the week."],
        },
    ]

    tasks = []
    for s in specs:
        pid = PROJECTS[s["project"]]
        hours = float(s["hours"])
        est = int(hours) if hours == int(hours) else hours
        tasks.append(
            {
                "title": s["title"],
                "description": s["description"],
                "taskType": "individual",
                "linkedCompanyId": COMPANY_ID,
                "department": "",
                "project": pid,
                "supervisor": "",
                "priority": "medium",
                "visibility": False,
                "startDate": s["start"].isoformat(),
                "deadline": s["deadline"].isoformat(),
                "estimatedHours": est,
                "isRecurring": False,
                "recurringFrequency": "",
                "supervisorNotes": "",
                "instructions": "",
                "allowFeedback": True,
                "allowRescheduling": False,
                "enableComments": True,
                "linkedWorkflow": "",
                "subtasks": make_subtasks(hours, s["title"][:40]),
                "assignedTo": [USER_ID],
                "relatedObjective": "",
                "status": "completed",
                "tags": [],
                "criteria": s["criteria"],
                "referenceLinks": [],
                "fileUrl": [],
                "fiscalYear": "2082/83",
                "nepaliStartDate": nepali(s["start"]),
                "nepaliDeadline": nepali(s["deadline"]),
                "progress": 100,
                "_meta_project_name": s["project"],
                "_meta_hours": hours,
            }
        )
    return tasks


def session_ok(page) -> bool:
    return "/login" not in page.url.lower() and "/user" in page.url.lower()


def get_bearer(page) -> str | None:
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
          // also scan sessionStorage
          for (const k of Object.keys(sessionStorage)) {
            const v = sessionStorage.getItem(k) || '';
            if (v.startsWith('eyJ')) return v;
          }
          return null;
        }"""
    )


def try_create(page, payload: dict, bearer: str | None) -> dict:
    clean = {k: v for k, v in payload.items() if not k.startswith("_meta")}
    result = page.evaluate(
        """async ({ body, bearer }) => {
          const headers = { 'Content-Type': 'application/json', Accept: 'application/json' };
          if (bearer) headers['Authorization'] = 'Bearer ' + bearer;
          const res = await fetch('/api/v1/user/tasks', {
            method: 'POST',
            credentials: 'include',
            headers,
            body: JSON.stringify(body),
          });
          const text = await res.text();
          let json = null;
          try { json = JSON.parse(text); } catch {}
          return { status: res.status, ok: res.ok, json, text: text.slice(0, 800) };
        }""",
        {"body": clean, "bearer": bearer},
    )
    return {"success": bool(result.get("ok")), "response": result}


def main() -> int:
    email = os.environ.get("PORTAL_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("PORTAL_PASSWORD", email)
    base = os.environ.get("PORTAL_URL", "https://founderp.ai").rstrip("/")
    dry = "--dry-run" in sys.argv

    tasks = build_gap_tasks()
    (OUT / "gap_tasks_payload.json").write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    log("info", f"Prepared {len(tasks)} gap tasks ({sum(t['_meta_hours'] for t in tasks):g}h total)")

    if dry:
        log("info", "Dry-run: payloads written, not posting.")
        for t in tasks:
            log("info", f"  {t['_meta_project_name']}: {t['title']} ({t['_meta_hours']}h) dl={t['deadline'][:10]}")
        return 0

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
            if not session_ok(page):
                do_login(page, base, "/login", email, password)
                page.goto(f"{base}/user/tasks", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                wait_for_page_ready(page)
            if not session_ok(page):
                log("error", "Not authenticated")
                return 1

            bearer = get_bearer(page)
            log("info", f"Bearer token {'found' if bearer else 'MISSING'}")

            created = []
            failed = []
            for t in tasks:
                log("info", f"Creating: {t['title']} ({t['_meta_hours']}h)")
                result = try_create(page, t, bearer)
                if result.get("success"):
                    tid = ((result.get("response") or {}).get("json") or {}).get("data", {}).get("_id")
                    log("info", f"  OK id={tid}")
                    created.append({"title": t["title"], "response": result["response"]})
                else:
                    msg = ((result.get("response") or {}).get("json") or {}).get("message")
                    log("error", f"  FAILED: {msg or result}")
                    failed.append({"title": t["title"], "result": result})
                page.wait_for_timeout(400)

            (OUT / "gap_create_results.json").write_text(
                json.dumps({"created": created, "failed": failed}, indent=2, default=str),
                encoding="utf-8",
            )
            context.storage_state(path=str(STATE_FILE))
            log("info", f"Done. created={len(created)} failed={len(failed)}")
            return 0 if not failed else 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
