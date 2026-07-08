# Automated Attendance Bot

Automates daily **clock-in (9:00 AM)** and **clock-out (6:00 PM)** on a Founderp-style
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

| File | Purpose |
|------|---------|
| `attendance_bot.py` | The Playwright bot (login, session reuse, action branching) |
| `.github/workflows/attendance.yml` | Cron schedule + manual trigger |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for local configuration |
| `FounderpAttendance.jsx` | Reference copy of the portal UI (selectors are based on it) |

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

## Bulk-create tasks on founderp.ai

| File | Purpose |
|------|---------|
| `tasks_bot.py` | Playwright bot — logs into founderp.ai and creates tasks from YAML |
| `tasks.yaml` | Current sprint tasks (commit this, then run the workflow) |
| `tasks.example.yaml` | Format reference |
| `.github/workflows/create-tasks.yml` | Manual GitHub Action to run the bot |

1. Edit `tasks.yaml` (defaults: `company`, `project`, `assignee`, `deadline_day`).
2. Push to `github.com/ssandesb/clocked`.
3. **Actions → Create Tasks → Run workflow** (use `dry_run: true` first to validate).
4. Requires secrets: `PORTAL_URL` (`https://founderp.ai`), `PORTAL_EMAIL`, `PORTAL_PASSWORD`.
