# Automated Attendance Bot

Automates daily **clock-in (9:00 AM)** and **clock-out (6:45 PM)** on a Founderp-style
employment portal using **Python 3.10+ / Playwright** (headless Chromium), scheduled by
**GitHub Actions** — with manual override from the GitHub mobile app.

## How it works (3 steps)

1. Opens `https://<your-portal>/login`
2. Fills email + password and signs in
   (skipped when the saved session in `state.json` is still valid)
3. Opens `https://<your-portal>/user/attendance` and clicks **Clock In** or **Clock Out**

The bot is idempotent: if the button is already pressed/missing it logs a warning,
closes the browser cleanly, and exits `0` without corrupting anything.

## Files

See **[SCRIPTS.md](SCRIPTS.md)** for the organized `bots/` layout and `python run.py …` commands.

| Path | Purpose |
|------|---------|
| `run.py` | Easy CLI launcher for all bots |
| `bots/attendance/` | Founderp clock-in / clock-out |
| `bots/tasks/` | Task create, hours report, CTO top-ups |
| `bots/linkedin/` | LinkedIn posting via Composio |
| `bots/cron/` | cron-job.org setup helpers |
| `bots/lib/` | Shared Founderp session + Composio helpers |
| `attendance_bot.py` | Thin shim → `bots.attendance.bot` (GitHub Actions) |
| `.github/workflows/attendance.yml` | Cron schedule + manual trigger |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for local configuration |

## Configuration (all dynamic — no hardcoding)

| Variable | Where | Default | Meaning |
|----------|-------|---------|---------|
| `PORTAL_URL` | **Secret** | — | Portal domain, e.g. `founderp.com` |
| `PORTAL_EMAIL` | **Secret** | `bajracharyasandeshh@gmail.com` | Login email |
| `PORTAL_PASSWORD` | **Secret** | same as email | Login password |
| `ATTENDANCE_TZ` | Repo **Variable** | `Asia/Kathmandu` | Timezone for shift times |
| `CLOCK_IN_TIME` | Repo **Variable** | `09:00` | Local clock-in time (HH:MM) |
| `CLOCK_OUT_TIME` | Repo **Variable** | `18:00` | Local clock-out time (HH:MM) |
| `TIME_TOLERANCE_MIN` | Repo **Variable** | `90` | Auto-mode matching window (minutes) |

## Portal URLs

| URL | Status | Use for bot? |
|-----|--------|--------------|
| **`https://founderp.ai`** | Login + attendance work | **Yes — set this as `PORTAL_URL` secret** |
| `https://cockedin.netlify.app` | Returns 404 on `/login` unless SPA is redeployed with `netlify.toml` | Only after redeploying this repo to Netlify |

Credentials on `founderp.ai`: email and password are both `bajracharyasandeshh@gmail.com`.

## GitHub Actions setup (step by step)

1. **Create a repo and push this folder**

   ```bash
   cd E:\erp_clone
   git init
   git add .
   git commit -m "Automated attendance bot"
   gh repo create attendance-bot --private --source . --push
   ```

2. **Add Encrypted Secrets**
   Repo → *Settings → Secrets and variables → Actions → New repository secret*:
   - `PORTAL_URL` → `https://founderp.ai` (production portal with login + attendance)
   - `PORTAL_EMAIL` → `bajracharyasandeshh@gmail.com`
   - `PORTAL_PASSWORD` → `bajracharyasandeshh@gmail.com`

3. **(Optional) Add Variables for dynamic times**
   Same page, *Variables* tab:
   - `CLOCK_IN_TIME` → e.g. `09:30`
   - `CLOCK_OUT_TIME` → e.g. `17:45`
   - `ATTENDANCE_TZ` → e.g. `Asia/Kathmandu`

   > GitHub cron itself is static, so if you change the times, also update the two
   > `cron:` lines in `.github/workflows/attendance.yml` (converted to **UTC**;
   > Nepal = UTC+5:45, so `09:00` NPT = `15 3 * * 1-5`). The `auto` mode then
   > double-checks the local time and picks the right action.

4. **Done.** The schedule runs Mon–Fri:
   - `15 3 * * 1-5` → 09:00 Nepal time → **Clock In**
   - `15 12 * * 1-5` → 18:00 Nepal time → **Clock Out**

## Manual override from your phone (GitHub iOS app)

1. Open the repo in the GitHub app → **Actions** tab
2. Select **Automated Attendance Bot** → **Run workflow**
3. Pick:
   - `action`: `clock-in`, `clock-out`, or `auto`
   - `portal_url`: optional domain override (e.g. `founderp.com`)
   - `force`: run even on weekends / outside time windows

## Run locally

```bash
pip install -r requirements.txt
playwright install chromium

# configure
copy .env.example .env    # then edit .env
# PowerShell: load .env into the session, or set vars directly:
$env:PORTAL_URL = "https://founderp.com"

python run.py attendance clock-in --force
python run.py attendance auto
# equivalent shim:
python attendance_bot.py --action clock-in --force
python attendance_bot.py --action auto
```

## Notes on session handling

- After every run the bot saves cookies/localStorage to `state.json`
  (cached between Actions runs via `actions/cache`).
- On start it first tries `/user/attendance` with the saved session;
  only if it gets bounced to `/login` does it re-enter credentials.
- The demo portal expires sessions every 5 minutes, so most scheduled runs
  will do a fresh login — that's expected and handled.

## cron-job.org 24/7 scheduler (9:00 AM + 6:45 PM Nepal)

Cloud cron calls **Composio directly** (no Netlify in the cron path). Composio then dispatches your GitHub workflow (`attendance.yml`), which runs `attendance_bot.py`.

```
cron-job.org (24/7)
  -> POST https://backend.composio.dev/api/v3.1/tools/execute/GITHUB_CREATE_A_WORKFLOW_DISPATCH_EVENT
     (header: x-api-key, body: inputs={action=clock-in|clock-out, force=true})
  -> Composio tool execution: GITHUB_CREATE_A_WORKFLOW_DISPATCH_EVENT
  -> ssandesb/clocked attendance.yml
  -> attendance_bot.py on founderp.ai
```

### One-time setup

1. **cron-job.org** ([dashboard](https://console.cron-job.org/dashboard)):
  - Create 2 jobs manually (timezone **Asia/Kathmandu**) and set:
    - Request method: `POST`
    - URL: `https://backend.composio.dev/api/v3.1/tools/execute/GITHUB_CREATE_A_WORKFLOW_DISPATCH_EVENT`
    - Header: `x-api-key: <your Composio Project API key>`
    - Request body (JSON):
      - `inputs.action = clock-in` for the 9:00 job
      - `inputs.action = clock-out` for the 18:45 job
      - `force = true`
  - Schedule:
    - **Attendance Clock In 9:00** — `0 9 * * *`
    - **Attendance Clock Out 18:45** — `45 18 * * *`

Notes:
- `setup_cronjobs.py` can create both routes; by default it creates the Composio-direct cron jobs (same as what we configured manually).

2. **Test locally** (Composio only, no cron):
   ```bash
   python cron_dispatch.py --action clock-in
   python cron_dispatch.py --action clock-out
   ```

## Calendar → GitHub clock-out trigger

Orchestrator that wires **Map (Google Calendar) → Brain (time gate) → Muscle (GitHub Actions)**:

1. Finds today's **Clock Out Trigger** event via Composio
2. Compares **now** to the event's exact `start.dateTime`
3. If early → **sleeps until that second/minute** (or `--no-wait` to skip for cron)
4. If `now >= start` → dispatches `attendance.yml` with `action=clock-out`

```bash
pip install -r requirements.txt
copy .env.example .env   # set COMPOSIO_API_KEY (and optional COMPOSIO_USER_ID)

python run.py attendance calendar-clockout              # wait until exact start, then dispatch
python run.py attendance calendar-clockout --no-wait    # skip if early (safe for frequent cron)
python run.py attendance calendar-clockout --dry-run    # find + wait, don't dispatch
```

Requires active Composio connections for **Google Calendar** and **GitHub** on that API key.

## Bulk-create tasks on founderp.ai

See **[SCRIPTS.md](SCRIPTS.md)**. Quick path:

```bash
python run.py tasks create --file bots/tasks/data/tasks.yaml --dry-run
python run.py tasks create --file bots/tasks/data/tasks.yaml
python run.py tasks report
```

YAML inputs live in `bots/tasks/data/`. GitHub Action: **Create Tasks** (default file `bots/tasks/data/tasks.yaml`).
Requires secrets: `PORTAL_URL` (`https://founderp.ai`), `PORTAL_EMAIL`, `PORTAL_PASSWORD`.
