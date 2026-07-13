#!/usr/bin/env python3
"""Create this week's Founderp tasks: Urja 20h + Bhumi 20h (Jenish), IC 10h (Sandesh)."""

from __future__ import annotations

from bots.lib.paths import REPO_ROOT

import json
import os
import sys
from datetime import date
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
from bots.tasks.hours_report import ad_to_bs

OUT = REPO_ROOT / "hours_probe"
OUT.mkdir(exist_ok=True)

SANDESH = "68ff1e1bcc52f7f335fef8ed"
JENISH = "68cbbdde25309930ae850165"
COMPANY_ID = "6879d57725c5683a4d213e7b"
PROJECTS = {
    "Urja Nepal": "6a27aa5505bd70cd716e742e",
    "Bhumi Finder": "69b79c0a6d393d213e9ce9cf",
    "Investment Circle": "69afb2d5296bd30a978ae256",
}

START = date(2026, 7, 13)
DEADLINE = date(2026, 7, 17)


def nepali(ad: date) -> dict:
    y, m, d = ad_to_bs(ad)
    return {"year": y, "month": m, "day": d}


def fmt_h(h: float) -> str:
    return str(int(h)) if float(h) == int(h) else str(h)


def subs(assignee: str, pairs: list[tuple[str, float]]) -> list[dict]:
    return [
        {
            "title": title,
            "assignedTo": assignee,
            "estimatedTime": fmt_h(hours),
            "completed": False,
        }
        for title, hours in pairs
    ]


def build_tasks() -> list[dict]:
    urja_pairs = [
        ("Public submit route + PublicMarketplaceSubmitPage shell", 2.5),
        ("Contact fields: submitter name + email validation", 1.5),
        ("Reuse MarketplaceMediaFields with public MinIO folders", 3),
        ("Reuse MarketplaceDocumentFields for public document uploads", 2.5),
        ("POST /api/content/marketplace-projects draft-only create", 3.5),
        ("Public upload endpoints restricted to marketplace/submissions/*", 2),
        ("Model fields: submitterName, submitterEmail, source=public", 1.5),
        ("Admin table: Submitted by column + Client draft badge", 1.5),
        ("Send to Client button copies /marketplace/submit link", 1),
        ("CORS/LAN + Vite proxy smoke for public form on phone network", 1),
    ]  # 20
    assert abs(sum(h for _, h in urja_pairs) - 20) < 0.01

    bhumi_pairs = [
        ("Audit logo PNG assets across agent + SuperAdmin shells", 2),
        ("Build sharp/imagemin resize pipeline for logo uploads (1x/2x/3x)", 3.5),
        ("Generate WebP + PNG fallbacks for brand logos", 2.5),
        ("Replace oversized homepage partner logos with resized variants", 2),
        ("Add Max dimension validation (e.g. 512px) on logo upload API", 2.5),
        ("SuperAdmin branding UI: preview resized logo before save", 2),
        ("Fix favicon + apple-touch-icon sizes from source PNG", 1.5),
        ("Compress agency profile logos without visible quality loss", 2),
        ("Document asset size guidelines for designers", 1),
        ("QA logos on retina + mobile agent header", 1),
    ]  # 20
    assert abs(sum(h for _, h in bhumi_pairs) - 20) < 0.01

    ic_pairs = [
        ("Meeting with Prakash — sprint priorities & handoff notes", 2),
        ("Follow up system admin checklist from last investor admin review", 2.5),
        ("Investor admin: verify My Investments vertical tabs default behavior", 2),
        ("Investor settings page QA after recent sprint tasks", 1.5),
        ("Sync Fund manager CRUD notes with Prakash for create-product selector", 1),
        ("Document open investor-admin follow-ups for next standup", 1),
    ]  # 10
    assert abs(sum(h for _, h in ic_pairs) - 10) < 0.01

    common = {
        "taskType": "individual",
        "linkedCompanyId": COMPANY_ID,
        "department": "",
        "supervisor": "",
        "priority": "medium",
        "visibility": False,
        "startDate": START.isoformat(),
        "deadline": DEADLINE.isoformat(),
        "isRecurring": False,
        "recurringFrequency": "",
        "supervisorNotes": "",
        "instructions": "",
        "allowFeedback": True,
        "allowRescheduling": False,
        "enableComments": True,
        "linkedWorkflow": "",
        "relatedObjective": "",
        "status": "todo",
        "tags": [],
        "referenceLinks": [],
        "fileUrl": [],
        "fiscalYear": "2082/83",
        "nepaliStartDate": nepali(START),
        "nepaliDeadline": nepali(DEADLINE),
    }

    return [
        {
            **common,
            "title": "Week 5 – Public Marketplace Client Submit Flow",
            "description": (
                "Implement the public marketplace draft submission flow for Nepal Urja: "
                "clients submit full project details (incl. media/docs) without SuperAdmin login; "
                "saves as draft with submitter name/email; admin Send to Client + review. "
                "Modular breakdown of the open-branch marketplace public submit work."
            ),
            "project": PROJECTS["Urja Nepal"],
            "assignedTo": [JENISH],
            "estimatedHours": 20,
            "criteria": [
                "Public /marketplace/submit creates draft projects with submitter contact; MinIO uploads work; admin can review and copy client link."
            ],
            "subtasks": subs(JENISH, urja_pairs),
            "_assignee_name": "Jenish Sharma",
            "_project_name": "Urja Nepal",
        },
        {
            **common,
            "title": "Week 13 – Brand Logo PNG Resize & Asset Pipeline",
            "description": (
                "Hypothetical but practical Bhumi Finder asset sprint: audit oversized logo PNGs, "
                "add resize/compress pipeline, WebP fallbacks, upload validation, and retina QA "
                "across agent + SuperAdmin branding surfaces."
            ),
            "project": PROJECTS["Bhumi Finder"],
            "assignedTo": [JENISH],
            "estimatedHours": 20,
            "criteria": [
                "Logo PNGs are resized/compressed with validation; branding previews work; mobile/retina QA signed off."
            ],
            "subtasks": subs(JENISH, bhumi_pairs),
            "_assignee_name": "Jenish Sharma",
            "_project_name": "Bhumi Finder",
        },
        {
            **common,
            "title": "Investor Admin Sync — Prakash Meeting & Follow-ups",
            "description": (
                "Investment Circle coordination week: meeting with Prakash, system-admin follow-ups, "
                "and investor-admin checks continuing from recent sprint items "
                "(My Investments tabs, investor settings, fund manager CRUD / create-product selector)."
            ),
            "project": PROJECTS["Investment Circle"],
            "assignedTo": [SANDESH],
            "estimatedHours": 10,
            "criteria": [
                "Prakash meeting notes captured; investor-admin and system-admin follow-ups documented for next sprint."
            ],
            "subtasks": subs(SANDESH, ic_pairs),
            "_assignee_name": "Sandesh Bajracharya",
            "_project_name": "Investment Circle",
        },
    ]


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
          return null;
        }"""
    )


def create_task(page, bearer: str | None, payload: dict) -> dict:
    body = {k: v for k, v in payload.items() if not k.startswith("_")}
    return page.evaluate(
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
          return { status: res.status, ok: res.ok, json, text: text.slice(0, 600) };
        }""",
        {"body": body, "bearer": bearer},
    )


def main() -> int:
    email = os.environ.get("PORTAL_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("PORTAL_PASSWORD", email)
    base = os.environ.get("PORTAL_URL", "https://founderp.ai").rstrip("/")

    tasks = build_tasks()
    (OUT / "this_week_tasks_payload.json").write_text(json.dumps(tasks, indent=2), encoding="utf-8")

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
            bearer = get_bearer(page)

            created = []
            failed = []
            for t in tasks:
                log(
                    "info",
                    f"Creating [{t['_project_name']}] {t['title']} "
                    f"({t['estimatedHours']}h → {t['_assignee_name']})",
                )
                resp = create_task(page, bearer, t)
                if resp.get("ok"):
                    tid = ((resp.get("json") or {}).get("data") or {}).get("_id")
                    log("info", f"  OK id={tid}")
                    created.append({"title": t["title"], "id": tid})
                else:
                    msg = ((resp.get("json") or {}).get("message")) or resp.get("text")
                    log("error", f"  FAIL {resp.get('status')} {msg}")
                    failed.append({"title": t["title"], "resp": resp})
                page.wait_for_timeout(400)

            (OUT / "this_week_create_results.json").write_text(
                json.dumps({"created": created, "failed": failed}, indent=2, default=str),
                encoding="utf-8",
            )
            context.storage_state(path=str(STATE_FILE))
            log("info", f"Done created={len(created)} failed={len(failed)}")
            return 0 if not failed else 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
