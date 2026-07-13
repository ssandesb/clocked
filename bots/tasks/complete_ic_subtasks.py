#!/usr/bin/env python3
"""Mark all pending Investment Circle subtasks as completed on Founderp."""

from __future__ import annotations

from bots.lib.paths import REPO_ROOT

import json
import os
import sys
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

OUT = REPO_ROOT / "hours_probe"
OUT.mkdir(exist_ok=True)
PROJECT = "Investment Circle"


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
          const init = { method, credentials: 'include', headers };
          if (body !== null && body !== undefined) {
            headers['Content-Type'] = 'application/json';
            init.body = JSON.stringify(body);
          }
          const res = await fetch(path, init);
          const text = await res.text();
          let json = null;
          try { json = JSON.parse(text); } catch {}
          return { status: res.status, ok: res.ok, json, text: text.slice(0, 800) };
        }""",
        {"method": method, "path": path, "bearer": bearer, "body": body},
    )


def assignee_id(task: dict) -> str | None:
    a = task.get("assignedTo")
    if isinstance(a, dict):
        return a.get("_id") or a.get("id")
    if isinstance(a, list) and a:
        first = a[0]
        if isinstance(first, dict):
            return first.get("_id") or first.get("id")
        return str(first)
    if isinstance(a, str):
        return a
    return None


def build_update(task: dict) -> dict:
    """Preserve task fields; mark every subtask completed."""
    aid = assignee_id(task)
    project = task.get("project")
    if isinstance(project, dict):
        project = project.get("_id") or project.get("id")

    subtasks = []
    for s in task.get("subtasks") or []:
        sub = {
            "title": s.get("title") or "Subtask",
            "estimatedTime": str(s.get("estimatedTime") or "1"),
            "completed": True,
        }
        if s.get("_id"):
            sub["_id"] = s["_id"]
        sa = s.get("assignedTo")
        if isinstance(sa, dict):
            sub["assignedTo"] = sa.get("_id") or sa.get("id") or aid
        elif isinstance(sa, str) and sa:
            sub["assignedTo"] = sa
        elif aid:
            sub["assignedTo"] = aid
        subtasks.append(sub)

    body = {
        "title": task.get("title"),
        "description": task.get("description") or "",
        "taskType": task.get("taskType") or "individual",
        "linkedCompanyId": task.get("linkedCompanyId") or "",
        "department": "",
        "project": project,
        "supervisor": "",
        "priority": task.get("priority") or "medium",
        "visibility": bool(task.get("visibility")),
        "estimatedHours": task.get("estimatedHours") or "",
        "isRecurring": bool(task.get("isRecurring")),
        "recurringFrequency": task.get("recurringFrequency") or "",
        "supervisorNotes": task.get("supervisorNotes") or "",
        "instructions": task.get("instructions") or "",
        "allowFeedback": task.get("allowFeedback", True),
        "allowRescheduling": task.get("allowRescheduling", False),
        "enableComments": task.get("enableComments", True),
        "linkedWorkflow": task.get("linkedWorkflow") or "",
        "subtasks": subtasks,
        "assignedTo": [aid] if aid else [],
        "relatedObjective": task.get("relatedObjective") or "",
        "status": "completed",
        "tags": task.get("tags") or [],
        "criteria": task.get("criteria") or ["Completed"],
        "referenceLinks": task.get("referenceLinks") or [],
        "fileUrl": task.get("fileUrl") or [],
        "fiscalYear": task.get("fiscalYear") or "2082/83",
        "progress": 100,
        "permissionStatus": task.get("permissionStatus") or "approved",
    }

    for key in ("startDate", "deadline", "nepaliStartDate", "nepaliDeadline"):
        if task.get(key) not in (None, ""):
            val = task[key]
            if key in ("startDate", "deadline") and isinstance(val, str) and "T" in val:
                val = val[:10]
            body[key] = val

    dept = task.get("department")
    if isinstance(dept, dict):
        body["department"] = dept.get("_id") or ""
    elif isinstance(dept, str):
        body["department"] = dept

    return body


def main() -> int:
    email = os.environ.get("PORTAL_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("PORTAL_PASSWORD", email)
    base = os.environ.get("PORTAL_URL", "https://founderp.ai").rstrip("/")

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
            listing = api(page, "GET", "/api/v1/user/tasks", bearer)
            tasks = (listing.get("json") or {}).get("data") or []
            ic = [t for t in tasks if ((t.get("project") or {}).get("name") == PROJECT)]

            targets = []
            for t in ic:
                pending = [s for s in (t.get("subtasks") or []) if not s.get("completed")]
                if pending:
                    targets.append((t, len(pending)))

            log("info", f"IC tasks={len(ic)}; with pending subtasks={len(targets)}")
            results = []
            marked = 0
            for task, pending_n in targets:
                tid = task.get("_id")
                title = task.get("title")
                body = build_update(task)
                log("info", f"Completing {pending_n} subtasks: {title!r}")
                resp = api(page, "PUT", f"/api/v1/user/tasks/{tid}", bearer, body)
                ok = bool(resp.get("ok"))
                if not ok:
                    resp = api(page, "PATCH", f"/api/v1/user/tasks/{tid}", bearer, body)
                    ok = bool(resp.get("ok"))
                msg = ((resp.get("json") or {}).get("message")) or resp.get("text", "")[:160]
                log("info" if ok else "error", f"  {'OK' if ok else 'FAIL'} {resp.get('status')} {msg}")
                if ok:
                    marked += pending_n
                results.append({"id": tid, "title": title, "pending": pending_n, "ok": ok, "status": resp.get("status")})
                page.wait_for_timeout(250)

            # Verify
            listing2 = api(page, "GET", "/api/v1/user/tasks", bearer)
            tasks2 = (listing2.get("json") or {}).get("data") or []
            still = 0
            for t in tasks2:
                if ((t.get("project") or {}).get("name") != PROJECT):
                    continue
                still += sum(1 for s in (t.get("subtasks") or []) if not s.get("completed"))

            summary = {
                "tasks_updated": sum(1 for r in results if r["ok"]),
                "tasks_failed": sum(1 for r in results if not r["ok"]),
                "subtasks_marked": marked,
                "pending_remaining": still,
                "results": results,
            }
            (OUT / "ic_complete_subtasks_results.json").write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )
            context.storage_state(path=str(STATE_FILE))
            log("info", f"Done. marked≈{marked}, pending_remaining={still}")
            return 0 if summary["tasks_failed"] == 0 and still == 0 else 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
