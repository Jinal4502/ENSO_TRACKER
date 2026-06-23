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
from render_dashboard import classify, render

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
    """One-paragraph change summary to include in the email."""
    if not previous:
        return "First run — baseline established."

    lines = []
    cur_anom  = current.get("latest_weekly", {}).get("nino34_anom")
    prev_anom = previous.get("latest_weekly", {}).get("nino34_anom")
    if cur_anom is not None and prev_anom is not None:
        delta = cur_anom - prev_anom
        direction = "rose" if delta > 0 else "fell"
        lines.append(
            f"Niño-3.4 anomaly {direction} {abs(delta):+.2f} °C "
            f"(was {prev_anom:+.2f}, now {cur_anom:+.2f})."
        )

    cur_status  = current.get("discussion", {}).get("status", "")
    prev_status = previous.get("discussion", {}).get("status", "")
    if cur_status and cur_status != prev_status:
        lines.append(f"Advisory status changed: {prev_status} → {cur_status}.")

    cur_oni  = current.get("latest_oni", {}).get("oni")
    prev_oni = previous.get("latest_oni", {}).get("oni")
    if cur_oni is not None and prev_oni is not None and cur_oni != prev_oni:
        lines.append(f"ONI updated to {cur_oni:+.2f} (was {prev_oni:+.2f}).")

    return " ".join(lines) if lines else "No significant changes this week."


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
    <a href="{pages_url}" style="display:inline-block;margin-top:16px;background:{color};color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:600;font-size:.9rem">
      View Full Dashboard →
    </a>
  </div>
  <div style="padding:12px 24px;background:#f6f8fa;font-size:.75rem;color:#888">
    Sources: NOAA/CPC · IRI Columbia · Australian BoM ·
    <a href="https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/">CPC Advisory</a>
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

    # 1. Fetch
    data = fetch_all()
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Data saved → {DATA_FILE}")

    # 2. Render dashboard
    render(data, DASHBOARD)

    # 3. History diff
    history = load_history()
    previous = history[-1] if history else None
    diff = diff_summary(data, previous)
    print(f"Change summary: {diff}")

    # Append snapshot (lightweight — only latest values + metadata)
    snapshot = {
        "fetched_utc":   data["fetched_utc"],
        "latest_weekly": data["latest_weekly"],
        "latest_oni":    data["latest_oni"],
        "latest_roni":   data["latest_roni"],
        "discussion":    data["discussion"],
    }
    history.append(snapshot)
    save_history(history)

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
