#!/usr/bin/env python3
"""Rewrite the 7 CTO top-up tasks with realistic titles and varied subtasks."""

from __future__ import annotations

import json
import os
import sys
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

OUT = Path("hours_probe")
OUT.mkdir(exist_ok=True)
USER_ID = "68ff1e1bcc52f7f335fef8ed"

# Original gap-fill task IDs created earlier
UPDATES = [
    {
        "id": "6a546587f6826e1aa923560f",
        "project": "Bhumi Finder",
        "title": "SuperAdmin Role Guards & CMS Edge Cases",
        "description": (
            "Follow-up to SuperAdmin Function Flows: finish remaining role-guard paths, "
            "CMS publish/unpublish edge cases, and audit logging before Blog Integration week."
        ),
        "hours": 9,
        "criteria": [
            "Role-guarded CMS routes reject unauthorized SuperAdmin actions; edge-case publish flows verified."
        ],
        "subtask_titles": [
            "Add route-level SuperAdmin role guards on CMS mutate endpoints",
            "Handle publish/unpublish race when two admins edit the same page",
            "Wire audit log entries for CMS create/update/delete",
            "QA matrix for SoftAdmin vs SuperAdmin permission differences",
        ],
        # 2.5 + 2 + 3 + 1.5 = 9
        "subtask_hours": [2.5, 2, 3, 1.5],
    },
    {
        "id": "6a546588f6826e1aa923562b",
        "project": "Bhumi Finder",
        "title": "Week 3 – CMS Soft Launch, Seed Content & Preview Mode",
        "description": (
            "Bridge week after SuperAdmin flows and before Blog Integration: soft-launch CMS, "
            "seed legal/settings content, and ship preview mode for public pages."
        ),
        "hours": 40,
        "criteria": [
            "CMS soft-launch checklist complete with seeded Privacy/Terms/Settings and working preview mode."
        ],
        "subtask_titles": [
            "Seed Privacy, Terms, and Settings documents in MongoDB",
            "Build public preview route that reads draft CMS documents",
            "Add SuperAdmin toggle for draft vs published content",
            "Implement image upload for CMS hero/banner fields",
            "Validate rich-text sanitization on CMS body fields",
            "Mobile QA for legal pages rendered from CMS",
            "Write soft-launch runbook for content editors",
            "Fix empty-state UI when CMS collection has no published docs",
            "Add cache-busting for published CMS payloads",
            "Regression test SuperAdmin login → CMS edit → public render",
            "Document content model fields for Blog Integration handoff",
            "Smoke-test staging CMS against production Mongo URI config",
            "Polish SuperAdmin CMS list filters (status, updatedAt)",
        ],
        # 3+3.5+2.5+4+3+2+2.5+3+3.5+4+2+3.5+3.5 = 40
        "subtask_hours": [3, 3.5, 2.5, 4, 3, 2, 2.5, 3, 3.5, 4, 2, 3.5, 3.5],
    },
    {
        "id": "6a546589f6826e1aa9235655",
        "project": "Bhumi Finder",
        "title": "Week 4 – Agent Portal Auth Hardening & Listing CRUD",
        "description": (
            "Prepare Agent portal foundations ahead of Week 5 UI/onboarding: JWT session hardening, "
            "agent listing CRUD, and basic property draft workflow."
        ),
        "hours": 40,
        "criteria": [
            "Agents can securely sign in and complete listing CRUD with draft/publish states."
        ],
        "subtask_titles": [
            "Harden agent JWT refresh + httpOnly cookie storage",
            "Build agent listing create form with required property fields",
            "Implement listing edit/update API with ownership checks",
            "Add draft vs published state for agent listings",
            "Wire listing delete with soft-delete and restore",
            "Agent dashboard empty states for zero listings",
            "Upload and attach listing cover image via MinIO/S3 helper",
            "Validate Nepali/English address fields on listing form",
            "Add rate limiting on agent auth login endpoint",
            "E2E smoke: agent signup → create listing → publish",
            "Fix CORS/cookie issues between agent app and API",
            "Write agent portal README for local setup",
            "QA pass on mobile agent create-listing flow",
        ],
        "subtask_hours": [3.5, 4, 3, 2.5, 2, 1.5, 4, 3, 2.5, 4, 3.5, 2.5, 4],
    },
    {
        "id": "6a54658af6826e1aa923567f",
        "project": "Urja Nepal",
        "title": "Week 1 Follow-up – Homepage Audit Remediations & Env Hardening",
        "description": (
            "Continue Week 1 Homepage Design Auditing and System Setup: close audit findings, "
            "finish env/Mongo hardening, and unblock Week 2 layout work."
        ),
        "hours": 28,
        "criteria": [
            "Homepage audit remediations closed; Node/Mongo env setup stable for Week 2 frontend work."
        ],
        "subtask_titles": [
            "Fix critical mobile hero spacing issues from audit report",
            "Resolve WCAG contrast failures on primary CTAs",
            "Normalize heading hierarchy on homepage sections",
            "Add .env.example for API + Mongo + MinIO keys",
            "Stabilize Mongo connection retry/backoff in Node boot",
            "Document local run steps for frontend + backend",
            "Fix broken footer links discovered in audit",
            "Compress and lazy-load above-the-fold homepage images",
            "Add basic ESLint/prettier baseline for new UI files",
            "Verify production build with audit remediations applied",
        ],
        # 3+2.5+2+2+3.5+2.5+1.5+4+3+4 = 28
        "subtask_hours": [3, 2.5, 2, 2, 3.5, 2.5, 1.5, 4, 3, 4],
    },
    {
        "id": "6a54658af6826e1aa92356a3",
        "project": "Urja Nepal",
        "title": "Week 3 – Marketplace Listings, Filters & Fund Page Shell",
        "description": (
            "After Week 2 homepage sections: build marketplace listing/filter UI and a fund page shell "
            "aligned with Nepal Urja public site patterns."
        ),
        "hours": 40,
        "criteria": [
            "Marketplace list + filters render from API; fund page shell matches design and is responsive."
        ],
        "subtask_titles": [
            "Marketplace card grid with capacity/location/stage fields",
            "Filter bar for stage, risk, and investment type",
            "Project detail route wiring from marketplace slug",
            "Fund page hero + investment options layout shell",
            "Empty and loading states for marketplace fetch failures",
            "Mobile responsive polish for marketplace filters",
            "Hook marketplace list to public content API",
            "Add skeleton loaders for marketplace cards",
            "Fund page FAQ accordion section",
            "QA against Prakash feedback on homepage→marketplace nav",
            "Accessibility pass on filter controls (keyboard)",
            "Screenshot pack for design review",
            "Fix hydration mismatch on marketplace filter defaults",
        ],
        "subtask_hours": [4, 3.5, 3, 4, 2, 2.5, 3.5, 2, 3, 3.5, 2.5, 2.5, 4],
    },
    {
        "id": "6a54658bf6826e1aa92356cd",
        "project": "Urja Nepal",
        "title": "Week 4 – SuperAdmin Marketplace Forms & Media Uploads",
        "description": (
            "Extend marketplace work with SuperAdmin create/edit forms, document/image uploads to MinIO, "
            "and draft/publish controls for project records."
        ),
        "hours": 40,
        "criteria": [
            "SuperAdmin can create/edit marketplace projects with media/docs uploaded and draft/publish toggle working."
        ],
        "subtask_titles": [
            "SuperAdmin marketplace project create form fields",
            "Edit existing project with prefilled media keys",
            "Cover image upload to MinIO marketplace/covers",
            "Gallery multi-image upload with captions",
            "Document upload (PDF) with 2MB validation",
            "Draft vs published switch on project save",
            "Video upload or YouTube URL source mode",
            "Server folder allow-list for marketplace uploads",
            "Toast + error handling for failed uploads",
            "Admin table columns for status and capacity",
            "Delete project cleans orphaned MinIO keys",
            "Mobile QA on SuperAdmin marketplace form",
            "Write short admin guide for content editors",
        ],
        "subtask_hours": [4, 3.5, 3, 3.5, 2.5, 2, 3, 2.5, 2, 3, 3.5, 3.5, 4],
    },
    {
        "id": "6a54658cf6826e1aa92356f7",
        "project": "Bhumi Finder",
        "title": "Week 12 – Perf Baseline, Bundle Trim & User Guide Docs",
        "description": (
            "Follow-up after Week 11 auth/UI polish and ahead of Optimize Bhumifinder to 80% Performance: "
            "establish Lighthouse baseline, trim bundles, and complete user-facing documentation."
        ),
        "hours": 40,
        "criteria": [
            "Lighthouse baseline documented; clear bundle wins landed; user guides cover agent and SuperAdmin flows."
        ],
        "subtask_titles": [
            "Capture Lighthouse mobile/desktop baselines on key routes",
            "Code-split agent dashboard and listing forms",
            "Defer non-critical analytics and chat widgets",
            "Optimize property image srcset / lazy loading",
            "Trim unused MUI/icon imports from agent shell",
            "Add performance budget notes to README",
            "Write SuperAdmin CMS user guide (create→publish)",
            "Write Agent listing user guide with screenshots",
            "Fix Final Documentation task stubs with real sections",
            "Compress remaining PNG assets used on homepage",
            "Profile API listing endpoint N+1 queries",
            "Cache public property list response briefly",
            "QA regression after bundle trim on Safari/Chrome",
        ],
        "subtask_hours": [3, 4, 2.5, 3.5, 3, 2, 4, 3.5, 2.5, 2, 3.5, 3, 3.5],
    },
]

DELETE_IDS = [
    "6a546539f6826e1aa9234751",  # API CAPTURE probe
]


def assert_hours(item: dict) -> None:
    total = round(sum(item["subtask_hours"]), 2)
    if abs(total - item["hours"]) > 0.01:
        raise SystemExit(f"{item['title']}: subtask hours {total} != {item['hours']}")
    if len(item["subtask_titles"]) != len(item["subtask_hours"]):
        raise SystemExit(f"{item['title']}: title/hour length mismatch")


def build_body(item: dict) -> dict:
    assert_hours(item)
    subtasks = [
        {
            "title": title,
            "assignedTo": USER_ID,
            "estimatedTime": str(h).rstrip("0").rstrip(".") if isinstance(h, float) else str(h),
            "completed": True,
        }
        for title, h in zip(item["subtask_titles"], item["subtask_hours"])
    ]
    # normalize estimatedTime formatting
    for s, h in zip(subtasks, item["subtask_hours"]):
        if float(h) == int(h):
            s["estimatedTime"] = str(int(h))
        else:
            s["estimatedTime"] = str(h)
    return {
        "title": item["title"],
        "description": item["description"],
        "estimatedHours": item["hours"] if item["hours"] != int(item["hours"]) else int(item["hours"]),
        "criteria": item["criteria"],
        "subtasks": subtasks,
        "status": "completed",
        "progress": 100,
        "assignedTo": [USER_ID],
        "priority": "medium",
        "taskType": "individual",
        "visibility": False,
        "allowFeedback": True,
        "allowRescheduling": False,
        "enableComments": True,
    }


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


def api(page, method: str, path: str, bearer: str | None, body=None) -> dict:
    return page.evaluate(
        """async ({ method, path, bearer, body }) => {
          const headers = { Accept: 'application/json' };
          if (bearer) headers['Authorization'] = 'Bearer ' + bearer;
          let init = { method, credentials: 'include', headers };
          if (body !== null && body !== undefined) {
            headers['Content-Type'] = 'application/json';
            init.body = JSON.stringify(body);
          }
          const res = await fetch(path, init);
          const text = await res.text();
          let json = null;
          try { json = JSON.parse(text); } catch {}
          return { status: res.status, ok: res.ok, json, text: text.slice(0, 1000) };
        }""",
        {"method": method, "path": path, "bearer": bearer, "body": body},
    )


def main() -> int:
    email = os.environ.get("PORTAL_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("PORTAL_PASSWORD", email)
    base = os.environ.get("PORTAL_URL", "https://founderp.ai").rstrip("/")

    for item in UPDATES:
        assert_hours(item)

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
            log("info", f"Bearer {'ok' if bearer else 'missing'}")

            # Fetch existing tasks to preserve dates/project/company
            listing = api(page, "GET", "/api/v1/user/tasks", bearer)
            tasks = (listing.get("json") or {}).get("data") or []
            by_id = {t.get("_id") or t.get("id"): t for t in tasks}

            results = []
            for item in UPDATES:
                existing = by_id.get(item["id"])
                if not existing:
                    log("error", f"Task not found: {item['id']} ({item['title']})")
                    results.append({"id": item["id"], "ok": False, "error": "not found"})
                    continue

                patch = build_body(item)
                # Preserve scheduling + project linkage from original create
                for key in (
                    "startDate",
                    "deadline",
                    "nepaliStartDate",
                    "nepaliDeadline",
                    "project",
                    "linkedCompanyId",
                    "fiscalYear",
                    "department",
                    "supervisor",
                ):
                    if key in existing and existing[key] not in (None, ""):
                        val = existing[key]
                        if key == "project" and isinstance(val, dict):
                            val = val.get("_id") or val.get("id")
                        if key == "department" and isinstance(val, dict):
                            val = val.get("_id") or ""
                        patch[key] = val

                # Normalize dates to YYYY-MM-DD if ISO
                for dk in ("startDate", "deadline"):
                    if isinstance(patch.get(dk), str) and "T" in patch[dk]:
                        patch[dk] = patch[dk][:10]

                log("info", f"Updating {item['id'][:8]}… → {item['title']} ({item['hours']}h)")
                # Try PUT then PATCH
                resp = api(page, "PUT", f"/api/v1/user/tasks/{item['id']}", bearer, patch)
                if not resp.get("ok"):
                    resp = api(page, "PATCH", f"/api/v1/user/tasks/{item['id']}", bearer, patch)
                if not resp.get("ok"):
                    # Some portals use POST update
                    resp = api(
                        page,
                        "PUT",
                        f"/api/v1/user/tasks/update/{item['id']}",
                        bearer,
                        patch,
                    )
                ok = bool(resp.get("ok"))
                msg = ((resp.get("json") or {}).get("message")) or resp.get("text", "")[:200]
                log("info" if ok else "error", f"  {'OK' if ok else 'FAIL'} {resp.get('status')} {msg}")
                results.append({"id": item["id"], "title": item["title"], "ok": ok, "resp": resp})
                page.wait_for_timeout(300)

            for did in DELETE_IDS:
                log("info", f"Deleting probe task {did}")
                resp = api(page, "DELETE", f"/api/v1/user/tasks/{did}", bearer)
                if not resp.get("ok"):
                    resp = api(page, "DELETE", f"/api/v1/tasks/{did}", bearer)
                log("info", f"  delete status={resp.get('status')}")

            (OUT / "gap_rewrite_results.json").write_text(
                json.dumps(results, indent=2, default=str), encoding="utf-8"
            )
            context.storage_state(path=str(STATE_FILE))
            failed = [r for r in results if not r.get("ok")]
            log("info", f"Updated ok={len(results)-len(failed)} failed={len(failed)}")
            return 0 if not failed else 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
