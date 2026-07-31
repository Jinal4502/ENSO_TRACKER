"""
fetch_impacts.py
Fetch and precompute all ENSO-impact data for the impacts page.
Outputs: docs/data/impacts_data.json

Data sources:
  ONI          — NOAA CPC full history (1950–present)
  GDP growth   — World Bank API  NY.GDP.MKTP.KD.ZG
  Food Prod    — World Bank API  AG.PRD.FOOD.XD
  Food Price   — FAO Food Price Index CSV (1990–present, monthly)
  Disasters    — EM-DAT CSV (optional; skip if docs/data/emdat.csv absent)
"""

import csv
import io
import json
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import stats as sp

# ── Config ────────────────────────────────────────────────────────────────────
OUT_DIR  = Path("docs/data")
OUT_FILE = OUT_DIR / "impacts_data.json"
EMDAT_CSV = OUT_DIR / "emdat.csv"

COUNTRIES = {
    "WLD": "World",
    "USA": "United States",
    "CHN": "China",
    "BRA": "Brazil",
    "IND": "India",
    "IDN": "Indonesia",
    "NGA": "Nigeria",
}

MAX_LAG = 5   # years

CONFOUND_EVENTS = [
    {"name": "1973 Oil Crisis",               "start": 1973, "end": 1975, "type": "economic"},
    {"name": "1980–82 Recession",             "start": 1980, "end": 1982, "type": "economic"},
    {"name": "1990–91 Gulf War / Recession",  "start": 1990, "end": 1991, "type": "both"},
    {"name": "1997–98 Asian Financial Crisis","start": 1997, "end": 1998, "type": "economic"},
    {"name": "2001 Dot-com Bust",             "start": 2001, "end": 2001, "type": "economic"},
    {"name": "2003 Iraq War",                 "start": 2003, "end": 2003, "type": "geopolitical"},
    {"name": "2008–09 Global Financial Crisis","start": 2008, "end": 2009, "type": "economic"},
    {"name": "2020 COVID Recession",          "start": 2020, "end": 2020, "type": "both"},
    {"name": "2022 Russia–Ukraine War",       "start": 2022, "end": 2022, "type": "geopolitical"},
]

_CONFOUND_YEARS = set()
for ev in CONFOUND_EVENTS:
    _CONFOUND_YEARS.update(range(ev["start"], ev["end"] + 1))


# ── Helpers ───────────────────────────────────────────────────────────────────

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ENSOTracker/1.0; research)"}

def _fetch_text(url: str) -> str:
    import requests as _req
    r = _req.get(url, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def _corr_pair(x: list, y: list) -> dict:
    """Pearson + Spearman for two aligned (no-NaN) lists."""
    if len(x) < 5:
        return {"pearson": None, "spearman": None, "n": len(x)}
    r_p, _ = sp.pearsonr(x, y)
    r_s, _ = sp.spearmanr(x, y)
    return {"pearson": round(r_p, 4), "spearman": round(r_s, 4), "n": len(x)}


def compute_lagged_corr(oni_annual: dict, metric_annual: dict, max_lag: int = MAX_LAG) -> list:
    """
    For each lag l in 0..max_lag compute correlation between oni[y] and metric[y+l].
    Returns list of dicts with lag, full-sample corr, and confound-excluded corr.
    """
    results = []
    for lag in range(max_lag + 1):
        years = sorted(set(oni_annual) & {y - lag for y in metric_annual})

        x_full, y_full = [], []
        x_excl, y_excl = [], []
        for y in years:
            o = oni_annual.get(y)
            m = metric_annual.get(y + lag)
            if o is None or m is None or np.isnan(o) or np.isnan(m):
                continue
            x_full.append(o)
            y_full.append(m)
            if y not in _CONFOUND_YEARS and (y + lag) not in _CONFOUND_YEARS:
                x_excl.append(o)
                y_excl.append(m)

        results.append({
            "lag":  lag,
            "full": _corr_pair(x_full, y_full),
            "excl": _corr_pair(x_excl, y_excl),
        })
    return results


# ── 1. ONI history ────────────────────────────────────────────────────────────

def fetch_oni_annual() -> dict:
    """
    Fetch full NOAA ONI table and return {year: mean_oni} over all 3-month seasons.
    NOAA format: YR  SEAS  TOTAL  CLIM  ANOM  ...
    """
    print("  Fetching ONI history from NOAA ...")
    url = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
    raw = _fetch_text(url)

    # Format: SEAS  YR  TOTAL  ANOM
    by_year = defaultdict(list)
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 4 or not parts[1].isdigit():
            continue
        year = int(parts[1])
        try:
            anom = float(parts[3])
        except ValueError:
            continue
        by_year[year].append(anom)

    return {yr: round(float(np.mean(vals)), 3) for yr, vals in sorted(by_year.items())}


# ── 2. World Bank API ─────────────────────────────────────────────────────────

def _fetch_wb(indicator: str) -> dict[str, dict[int, float]]:
    """
    Return {iso_code: {year: value}} for all COUNTRIES.
    """
    iso_str = ";".join(COUNTRIES.keys())
    url = (
        f"https://api.worldbank.org/v2/country/{iso_str}/indicator/{indicator}"
        f"?format=json&per_page=2000&date=1961:2024"
    )
    print(f"  Fetching World Bank {indicator} ...")
    raw = json.loads(_fetch_text(url))
    records = raw[1] if isinstance(raw, list) and len(raw) > 1 else []

    out: dict[str, dict[int, float]] = defaultdict(dict)
    for rec in records:
        iso  = rec.get("countryiso3code") or rec.get("country", {}).get("id", "")
        year = rec.get("date")
        val  = rec.get("value")
        if iso in COUNTRIES and year and val is not None:
            out[iso][int(year)] = float(val)
    return dict(out)


def fetch_gdp_growth() -> dict[str, dict[int, float]]:
    return _fetch_wb("NY.GDP.MKTP.KD.ZG")


def fetch_food_production() -> dict[str, dict[int, float]]:
    return _fetch_wb("AG.PRD.FOOD.XD")


# ── 3. FAO Food Price Index ───────────────────────────────────────────────────

def fetch_fao_fpi() -> dict:
    """
    Returns {
      "annual": {year: avg_composite},
      "sub_annual": {"cereals": {year: avg}, ...}
    }
    Monthly CSV columns: Date, Food Price Index, Meat, Dairy, Cereals, Oils, Sugar
    """
    url = (
        "https://www.fao.org/media/docs/worldfoodsituationlibraries/"
        "default-document-library/food_price_indices_data.csv"
    )
    print("  Fetching FAO Food Price Index ...")
    raw = _fetch_text(url)

    sub_keys = ["Meat", "Dairy", "Cereals", "Oils", "Sugar"]
    monthly_composite: dict[int, list[float]] = defaultdict(list)
    monthly_sub: dict[str, dict[int, list[float]]] = {k: defaultdict(list) for k in sub_keys}

    # CSV has 2 preamble rows before the actual column-header row
    lines = raw.splitlines()
    data_start = next(i for i, l in enumerate(lines) if l.startswith("Date"))
    reader = csv.DictReader(lines[data_start:])
    for row in reader:
        date_str = row.get("Date", "").strip()
        if not date_str or len(date_str) < 4:
            continue
        try:
            year = int(date_str[:4])
        except ValueError:
            continue
        try:
            composite = float(row["Food Price Index"])
            monthly_composite[year].append(composite)
        except (KeyError, ValueError):
            pass
        for k in sub_keys:
            try:
                monthly_sub[k][year].append(float(row[k]))
            except (KeyError, ValueError):
                pass

    def _annual_avg(d):
        return {yr: round(float(np.mean(vs)), 3) for yr, vs in sorted(d.items()) if vs}

    return {
        "annual":     _annual_avg(monthly_composite),
        "sub_annual": {k.lower(): _annual_avg(monthly_sub[k]) for k in sub_keys},
    }


# ── 4. EM-DAT (optional) ─────────────────────────────────────────────────────

def load_emdat():
    """
    Read EM-DAT CSV if present. Aggregate to annual global disaster count + damage.
    Expected columns (flexible): Year, Total Deaths, Total Damage ('000 US$), Disaster Type
    Returns {year: {count, damage_musd}} or None if file absent.
    """
    if not EMDAT_CSV.exists():
        print("  EM-DAT CSV not found — skipping disasters domain.")
        return None

    print(f"  Loading EM-DAT from {EMDAT_CSV} ...")
    counts: dict[int, int] = defaultdict(int)
    damage: dict[int, float] = defaultdict(float)

    with open(EMDAT_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Try common column name variants
            year_raw = row.get("Year") or row.get("year") or row.get("Dis Year") or ""
            dmg_raw  = (row.get("Total Damage, Adjusted ('000 US$)")
                        or row.get("Total Damage ('000 US$)")
                        or row.get("Total Damage")
                        or "0")
            try:
                year = int(str(year_raw).strip())
            except ValueError:
                continue
            counts[year] += 1
            try:
                damage[year] += float(str(dmg_raw).replace(",", "").strip() or "0")
            except ValueError:
                pass

    if not counts:
        return None

    result = {}
    for yr in sorted(set(counts) | set(damage)):
        result[yr] = {
            "count":       counts.get(yr, 0),
            "damage_musd": round(damage.get(yr, 0.0) / 1000, 2),  # → million USD
        }
    return result


# ── 5. Anomaly series ─────────────────────────────────────────────────────────

def yoy_pct_change(annual: dict[int, float]) -> dict[int, float]:
    """Year-over-year % change — equivalent to detrending an index."""
    out = {}
    for yr in sorted(annual):
        prev = annual.get(yr - 1)
        curr = annual.get(yr)
        if prev is not None and curr is not None and prev != 0:
            out[yr] = round((curr - prev) / abs(prev) * 100, 4)
    return out


# ── 6. Serialize helpers ──────────────────────────────────────────────────────

def _series_payload(annual: dict[int, float], oni: dict[int, float]) -> dict:
    years  = sorted(annual)
    values = [annual[y] for y in years]
    corr   = compute_lagged_corr(oni, annual)
    return {"years": years, "values": values, "corr": corr}


# ── Main ──────────────────────────────────────────────────────────────────────

def fetch_impacts_data() -> dict:
    print("Fetching ENSO Impacts data ...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    oni_annual    = fetch_oni_annual()
    gdp_raw       = fetch_gdp_growth()
    food_prod_raw = fetch_food_production()
    fpi           = fetch_fao_fpi()
    emdat         = load_emdat()

    # GDP: raw growth rates are already the detrended form
    gdp_domain = {}
    for iso, name in COUNTRIES.items():
        annual = gdp_raw.get(iso, {})
        if annual:
            gdp_domain[iso] = {"name": name, **_series_payload(annual, oni_annual)}

    # Food production: YoY % change to detrend the rising index
    food_prod_domain = {}
    for iso, name in COUNTRIES.items():
        annual_raw = food_prod_raw.get(iso, {})
        if annual_raw:
            annual = yoy_pct_change(annual_raw)
            food_prod_domain[iso] = {"name": name, **_series_payload(annual, oni_annual)}

    # FAO food price: YoY % change on the composite + sub-indices
    fpi_annual = yoy_pct_change(fpi["annual"])
    fpi_subs   = {k: yoy_pct_change(v) for k, v in fpi["sub_annual"].items()}
    fpi_domain = {
        "global": {
            "name": "Global",
            **_series_payload(fpi_annual, oni_annual),
            "sub_indices": {k: {"years": sorted(v), "values": [v[y] for y in sorted(v)]}
                            for k, v in fpi_subs.items()},
        }
    }

    # Disasters
    disasters_domain = None
    if emdat:
        count_series  = {yr: v["count"]        for yr, v in emdat.items()}
        damage_series = {yr: v["damage_musd"]  for yr, v in emdat.items()}
        disasters_domain = {
            "global": {
                "name": "Global",
                "count":       _series_payload(count_series,  oni_annual),
                "damage_musd": _series_payload(damage_series, oni_annual),
            }
        }

    payload = {
        "generated":       datetime.now(timezone.utc).isoformat(),
        "oni_annual":      oni_annual,
        "confound_events": CONFOUND_EVENTS,
        "domains": {
            "gdp":        {"label": "GDP Growth Rate (%)",           "countries": gdp_domain},
            "food_prod":  {"label": "Food Prod. Index YoY Change (%)", "countries": food_prod_domain},
            "food_price": {"label": "FAO Food Price Index YoY Change (%)", "countries": fpi_domain},
            "disasters":  {"label": "Global Disaster Count",          "countries": disasters_domain},
        },
    }

    with open(OUT_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved → {OUT_FILE}  ({OUT_FILE.stat().st_size // 1024} KB)")
    return payload


if __name__ == "__main__":
    fetch_impacts_data()
