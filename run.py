#!/usr/bin/env python3
"""
Easy launcher for erp_clone bots.

Examples:
  python run.py list
  python run.py attendance clock-in --force
  python run.py tasks report
  python run.py tasks create --file bots/tasks/data/tasks.yaml --dry-run
  python run.py tasks this-week
  python run.py tasks complete-ic
  python run.py linkedin prompt
  python run.py cron dispatch --action clock-out
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

COMMANDS: dict[str, dict[str, tuple[str, str]]] = {
    "attendance": {
        "clock-in": ("bots.attendance.bot", "Attendance clock-in"),
        "clock-out": ("bots.attendance.bot", "Attendance clock-out"),
        "auto": ("bots.attendance.bot", "Attendance auto (time-window)"),
        "calendar-clockout": ("bots.attendance.calendar_clockout", "Calendar-triggered clock-out"),
    },
    "tasks": {
        "create": ("bots.tasks.bulk_create", "Bulk-create tasks from YAML (UI bot)"),
        "report": ("bots.tasks.hours_report", "Weekly hours report (BS/AD, exclude IC)"),
        "gap": ("bots.tasks.create_gap", "Create historical week gap tasks via API"),
        "rewrite-gap": ("bots.tasks.rewrite_gap", "Rewrite gap tasks with realistic titles"),
        "this-week": ("bots.tasks.create_this_week", "Create this week's Urja/Bhumi/IC tasks"),
        "complete-ic": ("bots.tasks.complete_ic_subtasks", "Mark all IC subtasks completed"),
    },
    "linkedin": {
        "post": ("bots.linkedin.post_bot", "Gemini caption + LinkedIn post + email"),
        "prompt": ("bots.linkedin.prompt_bot", "Prompt-doc driven LinkedIn post"),
        "drive": ("bots.linkedin.drive_post_bot", "Drive-image LinkedIn post"),
    },
    "cron": {
        "dispatch": ("bots.cron.dispatch", "Dispatch attendance via Composio"),
        "setup-attendance": ("bots.cron.setup_attendance", "Create attendance cron-job.org jobs"),
        "setup-linkedin": ("bots.cron.setup_linkedin", "Create LinkedIn cron job"),
        "patch-linkedin": ("bots.cron.patch_linkedin", "Patch LinkedIn cron extendedData"),
        "setup-prompt": ("bots.cron.setup_prompt", "Create/patch prompt LinkedIn cron"),
        "patch-request": ("bots.cron.patch_request", "Low-level cron-job.org request patcher"),
    },
}


def print_list() -> None:
    print("Available commands:\n")
    for group, cmds in COMMANDS.items():
        print(f"  {group}/")
        for name, (_mod, desc) in cmds.items():
            print(f"    python run.py {group} {name:<18}  # {desc}")
        print()
    print("Pass-through flags go after the command, e.g.")
    print("  python run.py attendance clock-in --force")
    print("  python run.py tasks create --dry-run")
    print("\nFull reference: SCRIPTS.md")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help", "list"):
        print_list()
        return 0

    if len(argv) < 2:
        print("Usage: python run.py <group> <command> [args...]", file=sys.stderr)
        print_list()
        return 1

    group, command, *rest = argv
    if group not in COMMANDS or command not in COMMANDS[group]:
        print(f"Unknown command: {group} {command}", file=sys.stderr)
        print_list()
        return 1

    module, _desc = COMMANDS[group][command]

    if group == "attendance" and command in ("clock-in", "clock-out", "auto"):
        if "--action" not in rest:
            rest = ["--action", command, *rest]

    sys.argv = [module, *rest]
    mod = importlib.import_module(module)
    if not hasattr(mod, "main"):
        print(f"Module {module} has no main()", file=sys.stderr)
        return 1
    return int(mod.main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
