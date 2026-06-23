# ENSO Tracker

Automated weekly dashboard for El Niño / La Niña conditions, hosted free on **GitHub Pages** and emailed to you every Monday.

**Data sources:** NOAA/CPC 

---

## What it does

1. Pulls official ENSO data weekly (Niño-3.4 SST, ONI, detrended anomaly, CPC Advisory text)
2. Renders a single-file HTML dashboard with charts and regional impacts
3. Commits the updated dashboard to GitHub and deploys it to Pages
4. Emails a compact brief with a button linking to the live dashboard

---

## Setup (≈ 10 minutes)

### 1. Create the GitHub repository

1. Go to [github.com/new](https://github.com/new) and create a **public** repo named `enso-tracker` (public is required for free GitHub Pages)
2. Push this folder to it:
   ```bash
   git init
   git add .
   git commit -m "initial ENSO tracker"
   git remote add origin https://github.com/<your-username>/enso-tracker.git
   git push -u origin main
   ```

### 2. Enable GitHub Pages

1. In your repo → **Settings → Pages**
2. Source: **GitHub Actions** (not a branch)
3. Save

Your dashboard will be live at: `https://<your-username>.github.io/enso-tracker/`

### 3. Add email secrets

In your repo → **Settings → Secrets and variables → Actions → New repository secret**, add these five:

| Secret name | Value |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Your Gmail address (e.g. `you@gmail.com`) |
| `SMTP_PASS` | A **Gmail App Password** — *not* your regular password (see below) |
| `EMAIL_TO` | The address to receive the weekly brief |
| `PAGES_URL` | `https://<your-username>.github.io/enso-tracker/` |

**Getting a Gmail App Password:**
1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable 2-Step Verification if not already on
3. Search "App Passwords" → create one named "ENSO Tracker"
4. Copy the 16-character code — that is your `SMTP_PASS`

### 4. Fire the first run

Go to your repo → **Actions → ENSO Weekly Update → Run workflow → Run workflow**.

The workflow will:
- Fetch fresh ENSO data
- Render the dashboard to `docs/index.html`
- Commit and push
- Deploy to Pages
- Send you an email

After that, it runs automatically every **Monday at 14:00 UTC**.

---

## Running locally

```bash
# Fetch data and render dashboard (no email)
python update_enso.py

# Dashboard is at docs/index.html — open in any browser
open docs/index.html
```

With email:
```bash
SMTP_USER=you@gmail.com SMTP_PASS=xxxx EMAIL_TO=prof@asu.edu \
PAGES_URL=https://you.github.io/enso-tracker/ \
python update_enso.py
```

---

## File structure

```
.
├── fetch_enso.py          # pulls data from NOAA/CPC
├── render_dashboard.py    # renders docs/index.html
├── update_enso.py         # orchestrator (fetch → render → email)
├── enso_data.json         # latest raw data (auto-updated)
├── enso_history.json      # weekly snapshots for change detection (auto-updated)
├── docs/
│   └── index.html         # live dashboard (served by GitHub Pages)
└── .github/workflows/
    └── weekly_update.yml  # GitHub Actions schedule
```

---

## Customizing

- **Add recipients:** Change `EMAIL_TO` to a comma-separated list and split it in `update_enso.py`
- **Change schedule:** Edit the `cron:` line in `weekly_update.yml` (uses UTC)
- **Regional impacts:** Edit the `impacts_for()` function in `render_dashboard.py`

---

## Data sources

| Source | URL |
|---|---|
| NOAA/CPC Weekly SST | [wksst9120.for](https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for) |
| ONI Monthly | [oni.ascii.txt](https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt) |
| Detrended Niño-3.4 (RONI proxy) | [detrend.nino34.ascii.txt](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/detrend.nino34.ascii.txt) |
| CPC ENSO Advisory | [ensodisc.txt](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.txt) |
