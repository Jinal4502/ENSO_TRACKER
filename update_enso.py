"""
update_enso.py
Main orchestrator: fetch → render → detect changes → email brief.
Run locally or via GitHub Actions.
"""

import json
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from fetch_enso import fetch_all
from fetch_iri import fetch_strength_plot, get_iri_image_urls, fetch_iri_model_predictions
from fetch_hurricanes import fetch_hurricane_data
from fetch_precipitation import fetch_precipitation_data
from render_dashboard import classify, render
from render_hurricanes import render_hurricanes
from render_precipitation import render_precipitation

HISTORY_FILE = "enso_history.json"
DATA_FILE    = "enso_data.json"
DASHBOARD    = "docs/index.html"


def load_history() -> list[dict]:
    if Path(HISTORY_FILE).exists():
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []


def save_history(history: list[dict]) -> None:
    with open(HISTORY_FILE, "w") as f:
        json.dump(history[-104:], f, indent=2)  # keep ~2 years of weekly snapshots


def diff_summary(current: dict, previous: Optional[dict]) -> str:
    """Current conditions summary for the email body."""
    cur_date   = current.get("fetched_utc", "")[:10]
    cur_anom   = current.get("latest_weekly", {}).get("nino34_anom")
    cur_label, _ = classify(cur_anom or 0.0)
    cur_oni    = current.get("latest_oni", {}).get("oni")
    cur_status = current.get("discussion", {}).get("status", "")

    return (
        f"As of {cur_date}, the Niño-3.4 SST anomaly stands at {cur_anom:+.2f} °C, "
        f"indicative of {cur_label} conditions. "
        f"The Oceanic Niño Index (ONI) is {cur_oni:+.2f} °C. "
        f"Current NOAA/CPC advisory status: {cur_status}."
    )


def build_email_html(data: dict, diff: str, pages_url: str) -> str:
    lw    = data.get("latest_weekly", {})
    anom  = lw.get("nino34_anom", 0.0)
    label, color = classify(anom)
    disc  = data.get("discussion", {})
    date  = data.get("fetched_utc", "")[:10]

    return f"""
<html><body style="font-family:Arial,sans-serif;background:#f6f8fa;padding:24px">
<div style="max-width:560px;margin:auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1)">
  <div style="background:{color};padding:20px 24px">
    <h1 style="color:#fff;margin:0;font-size:1.2rem">ENSO Tracker — Weekly Update</h1>
    <p style="color:rgba(255,255,255,.85);margin:4px 0 0;font-size:.85rem">{date}</p>
  </div>
  <div style="padding:20px 24px">
    <p style="font-size:1.6rem;font-weight:700;color:{color};margin:0">{anom:+.2f} °C</p>
    <p style="margin:4px 0 16px;color:#555">{label} · {disc.get('status','')}</p>
    <p style="color:#333;font-size:.9rem;line-height:1.5">{diff}</p>
    <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">
      <a href="{pages_url}" style="display:inline-block;background:{color};color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:600;font-size:.9rem">
        View ENSO Dashboard →
      </a>
      <a href="{pages_url}hurricanes.html" style="display:inline-block;background:#1c2128;color:#c9d1d9;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:600;font-size:.9rem;border:1px solid #30363d">
        🌀 Cyclone Tracker →
      </a>
      <a href="{pages_url}precipitation.html" style="display:inline-block;background:#1c2128;color:#c9d1d9;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:600;font-size:.9rem;border:1px solid #30363d">
        🌧 Arizona Precipitation →
      </a>
    </div>
  </div>
  <div style="padding:12px 24px;background:#f6f8fa;font-size:.75rem;color:#888">
    Source: <a href="https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/">NOAA/CPC</a>
  </div>
</div>
</body></html>
"""


def send_email(subject: str, html_body: str) -> None:
    smtp_host   = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port   = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user   = os.environ["SMTP_USER"]
    smtp_pass   = os.environ["SMTP_PASS"]
    to_addrs    = [a.strip() for a in os.environ["EMAIL_TO"].split(",")]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = ", ".join(to_addrs)
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as s:
        s.starttls()
        s.login(smtp_user, smtp_pass)
        s.sendmail(smtp_user, to_addrs, msg.as_string())
    print(f"Email sent → {', '.join(to_addrs)}")


def main() -> None:
    pages_url = os.environ.get(
        "PAGES_URL",
        "https://<your-github-username>.github.io/<your-repo-name>/"
    )

    print("=== ENSO Tracker Update ===")

    # 1. Fetch NOAA/CPC data
    data = fetch_all()

    # 1b. Fetch IRI data
    print("Fetching IRI strength categories ...")
    data["iri_strength"] = fetch_strength_plot()
    data["iri_images"]   = get_iri_image_urls()

    pred = fetch_iri_model_predictions()
    if pred is None and Path(DATA_FILE).exists():
        try:
            with open(DATA_FILE) as f:
                prev = json.load(f)
            pred = prev.get("iri_model_predictions")
            if pred:
                print(f"  [INFO] Using cached model predictions ({len(pred)} records from previous run)")
        except Exception:
            pass
    data["iri_model_predictions"] = pred

    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Data saved → {DATA_FILE}")

    # 2. Render dashboard
    render(data, DASHBOARD)

    # 2b. Render hurricane page
    print("Generating hurricane page ...")
    hurricane_data = fetch_hurricane_data()
    render_hurricanes(hurricane_data, "docs/hurricanes.html")

    # 2c. Render precipitation page
    print("Generating precipitation page ...")
    prcp_meta = fetch_precipitation_data()
    render_precipitation(prcp_meta, "docs/precipitation.html")

    # 3. History — append current snapshot, then find last week's entry
    history = load_history()
    snapshot = {
        "fetched_utc":   data["fetched_utc"],
        "latest_weekly": data["latest_weekly"],
        "latest_oni":    data["latest_oni"],
        "latest_roni":   data["latest_roni"],
        "discussion":    data["discussion"],
    }
    history.append(snapshot)
    save_history(history)

    diff = diff_summary(data, None)
    print(f"Change summary: {diff}")

    # 4. Send email (skip if env vars not set — safe for local runs)
    if os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"):
        lw    = data.get("latest_weekly", {})
        anom  = lw.get("nino34_anom", 0.0)
        label, _ = classify(anom)
        subject = (
            f"ENSO Update {data['fetched_utc'][:10]}: "
            f"{label} ({anom:+.2f} °C)"
        )
        html_body = build_email_html(data, diff, pages_url)
        try:
            send_email(subject, html_body)
        except Exception as exc:
            print(f"[WARN] Email failed: {exc}", file=sys.stderr)
    else:
        print("SMTP_USER/SMTP_PASS not set — skipping email.")

    print("=== Done ===")


if __name__ == "__main__":
    main()
