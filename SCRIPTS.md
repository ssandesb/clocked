# Scripts guide (`bots/`)

All automation lives under `bots/`. Use the launcher from the repo root:

```bash
python run.py list
python run.py <group> <command> [flags...]
```

## Layout

```
bots/
  attendance/     # Founderp clock-in / clock-out
  tasks/          # Founderp tasks, hours reports, CTO top-ups
    data/         # tasks YAML inputs
    probes/       # one-off API/UI probes (debug)
  linkedin/       # LinkedIn posting via Composio
  cron/           # cron-job.org setup / patch helpers
  lib/            # shared Founderp session + Composio helpers
run.py            # easy CLI
```

Root `attendance_bot.py`, `tasks_bot.py`, `linkedin_*.py` are thin shims for GitHub Actions.

## Attendance

| Command | What it does |
|---|---|
| `python run.py attendance clock-in --force` | Clock in on founderp.ai |
| `python run.py attendance clock-out --force` | Clock out |
| `python run.py attendance auto` | Pick action from local time windows |
| `python run.py attendance calendar-clockout` | Google Calendar → dispatch clock-out |

Env: `PORTAL_URL`, `PORTAL_EMAIL`, `PORTAL_PASSWORD` (see `.env.example`).

## Tasks (Founderp)

| Command | What it does |
|---|---|
| `python run.py tasks report` | Weekly hours table (BS/AD), excludes Investment Circle |
| `python run.py tasks create --file bots/tasks/data/tasks.yaml` | UI bulk-create from YAML |
| `python run.py tasks create --dry-run` | Fill forms, don't submit |
| `python run.py tasks this-week` | Create this week's Urja 20h + Bhumi 20h + IC 10h |
| `python run.py tasks gap` | Create historical week top-up tasks (API) |
| `python run.py tasks rewrite-gap` | Rewrite gap tasks with realistic titles/subtasks |
| `python run.py tasks complete-ic` | Mark all pending IC subtasks completed |

YAML inputs: `bots/tasks/data/`.

Reports dump to `hours_probe/` (gitignored).

## LinkedIn

| Command | What it does |
|---|---|
| `python run.py linkedin post` | Generate + post + email |
| `python run.py linkedin prompt` | Prompt Google Doc driven post |
| `python run.py linkedin drive` | Drive image post |

## Cron setup

| Command | What it does |
|---|---|
| `python run.py cron dispatch --action clock-out` | Composio → GitHub attendance workflow |
| `python run.py cron setup-attendance` | Create attendance cron-job.org jobs |
| `python run.py cron setup-linkedin` | Create LinkedIn cron |
| `python run.py cron patch-linkedin` | Patch LinkedIn cron body/headers |
| `python run.py cron setup-prompt` | Prompt LinkedIn cron |

## Module form (same thing)

```bash
python -m bots.attendance.bot --action clock-in --force
python -m bots.tasks.hours_report
python -m bots.tasks.bulk_create --file bots/tasks/data/tasks.yaml
```
