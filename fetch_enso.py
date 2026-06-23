"""
fetch_enso.py
Pulls ENSO data from official NOAA/CPC sources and returns a structured dict.
All parsers fail gracefully — a missing source never crashes the run.
"""

import re
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional

# ── NOAA/CPC endpoints ─────────────────────────────────────────────────────
NINO34_WEEKLY = (
    "https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for"
)
ONI_MONTHLY = (
    "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
)
RONI_MONTHLY = (
    "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/"
    "ensostuff/detrend.nino34.ascii.txt"
)
ENSO_DISCUSSION = (
    "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/"
    "enso_advisory/ensodisc.txt"
)
def _fetch(url: str, timeout: int = 20) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ENSOTracker/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin-1")
    except Exception as exc:
        print(f"  [WARN] Could not fetch {url}: {exc}")
        return None


# ── Nino-3.4 weekly SST ────────────────────────────────────────────────────
def _split_sst_pair(token: str) -> tuple[float, float]:
    """
    Parse a concatenated SST+anomaly token like '26.5-0.2' or '28.3 0.3'.
    The anomaly has no separator when negative, one space when positive.
    """
    token = token.strip()
    # Find the second numeric value by looking for a sign or dot after the first number
    m = re.match(r"^(-?\d+\.\d+)\s*([+-]\d+\.\d+)$", token)
    if m:
        return float(m.group(1)), float(m.group(2))
    raise ValueError(f"Cannot parse SST pair: {token!r}")


def parse_nino34_weekly(text: str) -> list[dict]:
    """
    Returns list of {date, nino12, nino12_anom, nino3, nino3_anom,
                      nino34, nino34_anom, nino4, nino4_anom}
    from the fixed-width wksst9120.for file.
    Format per line: ' 14JUN2026     28.6 0.5     29.0 0.3     28.8 1.1     29.2 0.4'
    """
    records = []
    for line in text.splitlines():
        # Lines start with a date in col 1-9 like ' 02SEP1981'
        m = re.match(r"^\s*(\d{2}[A-Z]{3}\d{4})\s+(.+)$", line)
        if not m:
            continue
        try:
            date = datetime.strptime(m.group(1), "%d%b%Y").date().isoformat()
            # Rest of line contains 4 SST+ANOM pairs, space-separated within pair may vary
            # Use regex to grab all numeric tokens (handles -0.x run-together cases)
            nums = re.findall(r"[+-]?\d+\.\d+", m.group(2))
            if len(nums) < 8:
                continue
            records.append({
                "date":        date,
                "nino12":      float(nums[0]), "nino12_anom": float(nums[1]),
                "nino3":       float(nums[2]), "nino3_anom":  float(nums[3]),
                "nino34":      float(nums[4]), "nino34_anom": float(nums[5]),
                "nino4":       float(nums[6]), "nino4_anom":  float(nums[7]),
            })
        except (ValueError, IndexError):
            continue
    return records


# ── ONI monthly ────────────────────────────────────────────────────────────
def parse_oni(text: str) -> list[dict]:
    """
    Returns list of {year, season, sst, oni} from oni.ascii.txt.
    File format: SEAS YR TOTAL ANOM  (ANOM is the ONI value)
    """
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("SEAS"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            records.append({
                "year":   int(parts[1]),
                "season": parts[0],
                "sst":    float(parts[2]),   # raw 3-month mean SST
                "oni":    float(parts[3]),   # anomaly — this is the ONI
            })
        except (ValueError, IndexError):
            continue
    return records


# ── RONI / detrended Niño-3.4 monthly ─────────────────────────────────────
_MONTH_ABBR = ["","Jan","Feb","Mar","Apr","May","Jun",
                "Jul","Aug","Sep","Oct","Nov","Dec"]

def parse_roni(text: str) -> list[dict]:
    """
    Returns list of {year, month, season, roni} from detrend.nino34.ascii.txt.
    File format: YR MON TOTAL ClimAdjust ANOM
    ANOM is the detrended anomaly (used as RONI proxy).
    """
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("YR"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            yr  = int(parts[0])
            mon = int(parts[1])
            records.append({
                "year":   yr,
                "month":  mon,
                "season": _MONTH_ABBR[mon],
                "roni":   float(parts[4]),   # detrended anomaly
            })
        except (ValueError, IndexError):
            continue
    return records


# ── ENSO Diagnostic Discussion text ────────────────────────────────────────
def parse_discussion(text: str) -> dict:
    """
    Extracts: status (advisory/watch/none), synopsis paragraph, issued date.
    """
    result = {"status": "unknown", "synopsis": "", "issued": ""}

    # Issued date
    m = re.search(r"ISSUED\s+([A-Z][A-Za-z]+ \d{1,2},?\s+\d{4})", text, re.I)
    if m:
        result["issued"] = m.group(1).strip()

    # Advisory status — parse from "ENSO Alert System Status:" line
    # CPC uses non-ASCII ñ which may get mangled; match on the structural line instead
    m_status = re.search(r"ENSO Alert System Status:\s*(.+)", text, re.IGNORECASE)
    if m_status:
        raw = m_status.group(1).strip()
        # Normalize mangled ñ → n for matching, then assign canonical label
        raw_clean = raw.upper().replace("�", "N")
        if "EL NIN" in raw_clean and "ADVISORY" in raw_clean:
            result["status"] = "El Niño Advisory"
        elif "LA NIN" in raw_clean and "ADVISORY" in raw_clean:
            result["status"] = "La Niña Advisory"
        elif "EL NIN" in raw_clean and "WATCH" in raw_clean:
            result["status"] = "El Niño Watch"
        elif "LA NIN" in raw_clean and "WATCH" in raw_clean:
            result["status"] = "La Niña Watch"
        elif "NEUTRAL" in raw_clean:
            result["status"] = "ENSO-Neutral"
        else:
            result["status"] = raw  # fallback: use raw text

    # First substantive paragraph (synopsis)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 80]
    for p in paragraphs:
        if any(kw in p.upper() for kw in ["NINO", "NINA", "SST", "CONDITION", "FORECAST"]):
            result["synopsis"] = " ".join(p.split())[:800]
            break

    return result


# ── Top-level fetch ─────────────────────────────────────────────────────────
def fetch_all() -> dict:
    print("Fetching Niño-3.4 weekly SST ...")
    weekly_text = _fetch(NINO34_WEEKLY)
    weekly = parse_nino34_weekly(weekly_text) if weekly_text else []

    print("Fetching ONI monthly ...")
    oni_text = _fetch(ONI_MONTHLY)
    oni = parse_oni(oni_text) if oni_text else []

    print("Fetching RONI monthly ...")
    roni_text = _fetch(RONI_MONTHLY)
    roni = parse_roni(roni_text) if roni_text else []

    print("Fetching ENSO Diagnostic Discussion ...")
    disc_text = _fetch(ENSO_DISCUSSION)
    discussion = parse_discussion(disc_text) if disc_text else {}

    # Latest values for quick access
    latest_weekly = weekly[-1] if weekly else {}
    latest_oni    = next(
        (r for r in reversed(oni)  if abs(r["oni"])  < 10), {}
    )
    latest_roni   = next(
        (r for r in reversed(roni) if abs(r.get("roni", 99)) < 10 and r.get("roni") is not None), {}
    )

    return {
        "fetched_utc":   datetime.now(timezone.utc).isoformat(),
        "discussion":    discussion,
        "latest_weekly": latest_weekly,
        "latest_oni":    latest_oni,
        "latest_roni":   latest_roni,
        "weekly_history": weekly[-52:],   # last 52 weeks for the chart
        "oni_history":    oni[-36:],       # last 3 years
        "roni_history":   roni[-36:],
    }


if __name__ == "__main__":
    data = fetch_all()
    print(json.dumps(data, indent=2))
