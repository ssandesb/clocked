#!/usr/bin/env python3
from __future__ import annotations

import json
import os

from playwright.sync_api import sync_playwright

from bots.lib.founderp_session import (
    DEFAULT_EMAIL,
    NAV_TIMEOUT_MS,
    STATE_FILE,
    do_login,
    wait_for_page_ready,
)

base = os.environ.get("PORTAL_URL", "https://founderp.ai").rstrip("/")
email = os.environ.get("PORTAL_EMAIL", DEFAULT_EMAIL)
password = os.environ.get("PORTAL_PASSWORD", email)

base_body = {
    "title": "API probe",
    "project": "69b79c0a6d393d213e9ce9cf",
    "linkedCompanyId": "6879d57725c5683a4d213e7b",
    "deadline": "2026-07-10T00:00:00.000Z",
    "startDate": "2026-07-06T00:00:00.000Z",
    "priority": "medium",
    "taskType": "individual",
    "criteria": ["x"],
    "estimatedHours": "1",
    "subtasks": [{"title": "s", "estimatedTime": "1"}],
    "nepaliStartDate": {"year": 2083, "month": 3, "day": 22},
    "nepaliDeadline": {"year": 2083, "month": 3, "day": 26},
}

variants = [
    {"assignedTo": "68ff1e1bcc52f7f335fef8ed"},
    {"assignedTo": "68ff1e1bcc52f7f335fef8ef"},
    {"assignedTo": {"_id": "68ff1e1bcc52f7f335fef8ed"}},
    {"assignees": ["68ff1e1bcc52f7f335fef8ed"]},
    {"assignedUsers": ["68ff1e1bcc52f7f335fef8ed"]},
    {"user": "68ff1e1bcc52f7f335fef8ed"},
    {"assignTo": "68ff1e1bcc52f7f335fef8ed"},
]

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        ignore_https_errors=True,
        storage_state=str(STATE_FILE) if STATE_FILE.exists() else None,
    )
    page = ctx.new_page()
    page.goto(f"{base}/user/tasks", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    wait_for_page_ready(page)
    if "/login" in page.url.lower():
        do_login(page, base, "/login", email, password)

    # Capture real UI POST by watching network after we submit a real form later
    for i, v in enumerate(variants):
        body = {**base_body, **v}
        r = page.evaluate(
            """async (body) => {
              const res = await fetch('/api/v1/user/tasks', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
              });
              const text = await res.text();
              let json = null;
              try { json = JSON.parse(text); } catch {}
              return { status: res.status, message: (json && (json.message || json.error)) || text.slice(0, 240) };
            }""",
            body,
        )
        print(i + 1, v, "->", r)

    # List employees to confirm IDs
    emps = page.evaluate(
        """async () => {
          const res = await fetch('/api/v1/user/employee?limit=50', { credentials: 'include' });
          return await res.json();
        }"""
    )
    data = emps.get("data") if isinstance(emps, dict) else emps
    if isinstance(data, dict):
        data = data.get("employees") or data.get("docs") or data.get("items") or []
    for e in (data or [])[:20]:
        name = e.get("name") or e.get("fullName")
        if name and "Sandesh" in str(name):
            print("EMP", json.dumps({k: e.get(k) for k in ("_id", "id", "name", "userId", "user", "email")}, default=str))

    browser.close()
