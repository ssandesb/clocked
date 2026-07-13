#!/usr/bin/env python3
"""
Calendar → GitHub attendance dispatcher (Map → Brain → Muscle).

Map:   find today's "Clock Out Trigger" event via Composio / Google Calendar
Brain: only proceed when now >= event start.dateTime (wait / skip until then)
Muscle: dispatch ssandesb/clocked Automated Attendance Bot (clock-out)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Kathmandu"
DEFAULT_EVENT_TITLE = "Clock Out Trigger"
DEFAULT_OWNER = "ssandesb"
DEFAULT_REPO = "clocked"
DEFAULT_WORKFLOW = "attendance.yml"
DEFAULT_REF = "main"
DEFAULT_LOOKAHEAD_HOURS = 24
DEFAULT_LOOKBACK_HOURS = 2
POLL_CHUNK_SEC = 15


def log(level: str, msg: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {level.upper():7s} {msg}", flush=True)


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no extra dependency). Does not override existing env."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val


def parse_rfc3339(raw: str) -> datetime:
    """Parse Google Calendar dateTime (RFC3339) into an aware datetime."""
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Python <3.11 needs the colon form offset; fromisoformat handles +05:45.
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().casefold()


def titles_match(event_title: str, wanted: str) -> bool:
    a = normalize_title(event_title)
    b = normalize_title(wanted)
    return a == b or b in a or a in b


@dataclass
class TriggerEvent:
    event_id: str
    title: str
    start: datetime
    end: datetime | None
    calendar: str | None = None
    display_url: str | None = None


def _dig_events(payload: object) -> list[dict]:
    """Normalize various Composio / Calendar response shapes into event dicts."""
    if payload is None:
        return []
    if isinstance(payload, list):
        out: list[dict] = []
        for item in payload:
            out.extend(_dig_events(item))
        return out
    if not isinstance(payload, dict):
        return []

    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return _dig_events(data) if isinstance(data, list) else []

    collected: list[dict] = []

    summary = data.get("summary_view")
    if isinstance(summary, list):
        for row in summary:
            if isinstance(row, dict):
                collected.append(row)

    events = data.get("events")
    if isinstance(events, list):
        for item in events:
            if not isinstance(item, dict):
                continue
            # Wrapped: {"event": {...}} or flat event
            ev = item.get("event") if isinstance(item.get("event"), dict) else item
            collected.append(ev)

    items = data.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                collected.append(item)

    return collected


def _event_start_raw(ev: dict) -> str | None:
    for key in ("start", "start_time", "startTime"):
        val = ev.get(key)
        if isinstance(val, str) and "T" in val:
            return val
        if isinstance(val, dict):
            # Prefer exact timed start.dateTime; reject all-day-only date.
            dt = val.get("dateTime") or val.get("date_time")
            if isinstance(dt, str) and dt:
                return dt
    return None


def _event_end_raw(ev: dict) -> str | None:
    for key in ("end", "end_time", "endTime"):
        val = ev.get(key)
        if isinstance(val, str) and "T" in val:
            return val
        if isinstance(val, dict):
            dt = val.get("dateTime") or val.get("date_time")
            if isinstance(dt, str) and dt:
                return dt
    return None


def _event_title(ev: dict) -> str:
    for key in ("title", "summary", "name"):
        val = ev.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def to_trigger_event(ev: dict) -> TriggerEvent | None:
    start_raw = _event_start_raw(ev)
    if not start_raw:
        return None  # all-day / missing timed start — not usable for exact minute
    title = _event_title(ev)
    if not title:
        return None
    end_raw = _event_end_raw(ev)
    return TriggerEvent(
        event_id=str(ev.get("event_id") or ev.get("id") or ""),
        title=title,
        start=parse_rfc3339(start_raw),
        end=parse_rfc3339(end_raw) if end_raw else None,
        calendar=ev.get("calendar") if isinstance(ev.get("calendar"), str) else None,
        display_url=ev.get("display_url") if isinstance(ev.get("display_url"), str) else None,
    )


def execute_tool(client, slug: str, arguments: dict, user_id: str | None) -> dict:
    kwargs: dict = {
        "slug": slug,
        "arguments": arguments,
        "dangerously_skip_version_check": True,
    }
    if user_id:
        kwargs["user_id"] = user_id
    result = client.tools.execute(**kwargs)
    if not isinstance(result, dict):
        result = {"data": result}
    if result.get("successful") is False:
        err = result.get("error") or result.get("data") or result
        raise RuntimeError(f"{slug} failed: {err}")
    return result


def find_clock_out_trigger(
    client,
    *,
    tz: ZoneInfo,
    title: str,
    user_id: str | None,
    lookback_hours: int,
    lookahead_hours: int,
) -> TriggerEvent | None:
    now = datetime.now(tz)
    time_min = (now - timedelta(hours=lookback_hours)).isoformat()
    time_max = (now + timedelta(hours=lookahead_hours)).isoformat()

    log("info", f"Listing calendar events {time_min} → {time_max}")
    raw = execute_tool(
        client,
        "GOOGLECALENDAR_EVENTS_LIST_ALL_CALENDARS",
        {
            "time_min": time_min,
            "time_max": time_max,
            "single_events": True,
            "show_deleted": False,
            "response_detail": "full",
            "q": title,
        },
        user_id,
    )

    candidates: list[TriggerEvent] = []
    for ev in _dig_events(raw):
        tev = to_trigger_event(ev)
        if tev is None:
            continue
        if not titles_match(tev.title, title):
            continue
        candidates.append(tev)

    if not candidates:
        # Retry without q in case free-text search missed the title.
        raw2 = execute_tool(
            client,
            "GOOGLECALENDAR_EVENTS_LIST_ALL_CALENDARS",
            {
                "time_min": time_min,
                "time_max": time_max,
                "single_events": True,
                "show_deleted": False,
                "response_detail": "full",
            },
            user_id,
        )
        for ev in _dig_events(raw2):
            tev = to_trigger_event(ev)
            if tev is None:
                continue
            if not titles_match(tev.title, title):
                continue
            candidates.append(tev)

    if not candidates:
        return None

    # Prefer the soonest upcoming (or most recent past) event.
    candidates.sort(key=lambda e: e.start)
    upcoming = [e for e in candidates if e.start >= now - timedelta(minutes=1)]
    chosen = upcoming[0] if upcoming else candidates[-1]
    return chosen


def wait_until_start(start: datetime, *, no_wait: bool) -> bool:
    """
    Return True if we are allowed to dispatch.

    Compares current time to the event's exact start.dateTime.
    If early and no_wait: skip (False).
    If early and waiting: sleep until the exact minute hits, then True.
    """
    # Align to whole seconds; dispatch as soon as now >= start.
    while True:
        now = datetime.now(timezone.utc).astimezone(start.tzinfo)
        if now >= start:
            log("info", f"Time gate open: now={now.isoformat()} >= start={start.isoformat()}")
            return True

        remaining = start - now
        secs = max(1, int(remaining.total_seconds()))
        # "Exact minute" — if we're in the same calendar minute already, don't delay further
        # beyond the second-level start; otherwise sleep until start (chunked).
        if no_wait:
            log(
                "warn",
                f"Early by {remaining}: now={now.isoformat()} < start={start.isoformat()} "
                "(--no-wait: skip).",
            )
            return False

        chunk = min(POLL_CHUNK_SEC, secs)
        log(
            "info",
            f"Waiting for exact start ({remaining} left). Sleeping {chunk}s...",
        )
        time.sleep(chunk)


def dispatch_clock_out(
    client,
    *,
    owner: str,
    repo: str,
    workflow_id: str,
    ref: str,
    user_id: str | None,
    force: bool,
) -> dict:
    inputs = {"action": "clock-out", "force": force}
    log("info", f"Dispatching {owner}/{repo} workflow={workflow_id} ref={ref} inputs={inputs}")
    return execute_tool(
        client,
        "GITHUB_CREATE_A_WORKFLOW_DISPATCH_EVENT",
        {
            "owner": owner,
            "repo": repo,
            "workflow_id": workflow_id,
            "ref": ref,
            # Composio GitHub tool expects inputs as a JSON string.
            "inputs": json.dumps(inputs),
        },
        user_id,
    )


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Dispatch attendance clock-out when Calendar 'Clock Out Trigger' start time is reached."
    )
    parser.add_argument(
        "--event-title",
        default=os.environ.get("CLOCK_OUT_EVENT_TITLE", DEFAULT_EVENT_TITLE),
        help='Calendar event title to match (default: "Clock Out Trigger").',
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="If current time is before start.dateTime, exit without dispatching (for cron).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Find + wait, but do not dispatch GitHub Actions.",
    )
    parser.add_argument("--force", action="store_true", default=True)
    parser.add_argument("--no-force", action="store_true", help="Pass force=false to the workflow.")
    args = parser.parse_args()

    api_key = os.environ.get("COMPOSIO_API_KEY", "").strip()
    if not api_key:
        log("error", "COMPOSIO_API_KEY is not set (add it to .env).")
        return 1

    tz_name = os.environ.get("ATTENDANCE_TZ", DEFAULT_TZ)
    tz = ZoneInfo(tz_name)
    user_id = os.environ.get("COMPOSIO_USER_ID") or None
    owner = os.environ.get("GITHUB_OWNER", DEFAULT_OWNER)
    repo = os.environ.get("GITHUB_REPO", DEFAULT_REPO)
    workflow_id = os.environ.get("GITHUB_WORKFLOW", DEFAULT_WORKFLOW)
    ref = os.environ.get("GITHUB_REF", DEFAULT_REF)
    lookback = int(os.environ.get("CALENDAR_LOOKBACK_HOURS", DEFAULT_LOOKBACK_HOURS))
    lookahead = int(os.environ.get("CALENDAR_LOOKAHEAD_HOURS", DEFAULT_LOOKAHEAD_HOURS))
    force = not args.no_force

    from composio import Composio

    client = Composio(api_key=api_key)

    event = find_clock_out_trigger(
        client,
        tz=tz,
        title=args.event_title,
        user_id=user_id,
        lookback_hours=lookback,
        lookahead_hours=lookahead,
    )
    if event is None:
        log("warn", f'No timed "{args.event_title}" event found in the search window.')
        return 0

    log(
        "info",
        f'Found "{event.title}" id={event.event_id or "?"} '
        f"start.dateTime={event.start.isoformat()}"
        + (f" url={event.display_url}" if event.display_url else ""),
    )

    if not wait_until_start(event.start, no_wait=args.no_wait):
        return 0

    if args.dry_run:
        log("info", "Dry run — would dispatch clock-out now.")
        return 0

    result = dispatch_clock_out(
        client,
        owner=owner,
        repo=repo,
        workflow_id=workflow_id,
        ref=ref,
        user_id=user_id,
        force=force,
    )
    log("info", f"Dispatch OK: {json.dumps(result.get('data', result), default=str)[:500]}")
    log(
        "info",
        f"Check runs: https://github.com/{owner}/{repo}/actions/workflows/{workflow_id}",
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("warn", "Interrupted.")
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 — top-level CLI boundary
        log("error", str(exc))
        sys.exit(1)
