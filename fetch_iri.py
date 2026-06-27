"""
fetch_iri.py
Fetches IRI ENSO forecast data:
  - Strength categories (Plotly JSON with binary-encoded arrays)
  - Image URLs for IRI/CPC figures 1-3 and SST model plume
"""

import base64
import json
import math
import struct
import urllib.request
from datetime import datetime, timezone
from typing import Optional


def _fetch_bytes(url: str, timeout: int = 20) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ENSOTracker/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as exc:
        print(f"  [WARN] Could not fetch {url}: {exc}")
        return None


def _decode_bdata(encoded: str, dtype: str) -> list:
    """Decode Plotly's base64-encoded typed binary array."""
    binary = base64.b64decode(encoded)
    fmt_map = {"i1": "b", "i2": "h", "i4": "i", "f4": "f", "f8": "d"}
    fmt_char = fmt_map.get(dtype, "b")
    n = len(binary) // struct.calcsize(fmt_char)
    return list(struct.unpack(f"<{n}{fmt_char}", binary))


# Canonical colors for each ENSO strength category (La Niña blue → Neutral green → El Niño red)
STRENGTH_COLORS = [
    "#1a237e",  # Very Strong La Niña
    "#1565c0",  # Strong La Niña
    "#1e88e5",  # Moderate La Niña
    "#90caf9",  # Weak La Niña
    "#66bb6a",  # Neutral
    "#ffee58",  # Weak El Niño
    "#ffa726",  # Moderate El Niño
    "#ef5350",  # Strong El Niño
    "#b71c1c",  # Very Strong El Niño
]


def _find_model_count(season_percents: list) -> int:
    """Back-calculate total model count from integer percentages.
    IRI ensembles have 25-35 models; start search at 25 to skip spurious small solutions."""
    for n in range(25, 50):
        if sum(round(p * n / 100) for p in season_percents) == n:
            return n
    return 26  # IRI default fallback


def fetch_iri_model_predictions() -> Optional[list]:
    """
    Use Playwright to open the IRI SST table page, wait for Highcharts to render,
    then extract model/season/anomaly data via JavaScript.
    Returns list of {model, season, nino34_anomaly} dicts, or None on failure.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [WARN] playwright not installed — skipping SST model predictions")
        return None

    print("Fetching IRI SST model predictions via Playwright ...")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()
        try:
            page.goto(
                "https://iri.columbia.edu/our-expertise/climate/forecasts/"
                "enso/current/?enso_tab=enso-sst_table",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            page.wait_for_function(
                "typeof Highcharts !== 'undefined' && Highcharts.charts.filter(Boolean).length > 0",
                timeout=30000,
            )
            page.wait_for_timeout(2000)   # brief settle for all series to render
            records = page.evaluate("""
            () => {
                // Standard ENSO 3-month season labels — skip time-axis historical data
                const SEASONS = new Set([
                    'MAM','AMJ','MJJ','JJA','JAS','ASO','SON','OND','NDJ','DJF','JFM','FMA',
                    'May-OBS','MAM-OBS'
                ]);
                const out = [];
                if (typeof Highcharts === 'undefined') return out;
                // Target only charts that use category x-axis (the SST plume chart)
                Highcharts.charts.filter(Boolean).forEach(chart => {
                    const hasCategories = chart.xAxis[0] && chart.xAxis[0].categories;
                    if (!hasCategories) return;
                    chart.series.forEach(series => {
                        series.data.forEach(point => {
                            const season = point.category || String(point.x);
                            if (!SEASONS.has(season)) return;
                            if (point.y === null || point.y === undefined) return;
                            out.push({
                                model:          series.name,
                                season:         season,
                                nino34_anomaly: point.y,
                            });
                        });
                    });
                });
                return out;
            }
            """)
            print(f"  Fetched {len(records)} model-season data points")
            # Sanitize: ensure all values are JSON-serializable primitives
            clean = []
            for rec in records:
                v = rec.get("nino34_anomaly")
                try:
                    v_f = float(v) if v is not None else None
                    if v_f is not None and (math.isnan(v_f) or math.isinf(v_f)):
                        v_f = None
                except (TypeError, ValueError):
                    v_f = None
                clean.append({
                    "model":          str(rec.get("model", "")),
                    "season":         str(rec.get("season", "")),
                    "nino34_anomaly": v_f,
                })
            return clean if clean else None
        except Exception as exc:
            import traceback
            print(f"  [WARN] Playwright fetch failed: {exc}")
            traceback.print_exc()
            return None
        finally:
            browser.close()


def fetch_strength_plot() -> Optional[dict]:
    """
    Fetch ENSO strength categories from IRI's Plotly endpoint.
    URL pattern: /strength_plot/{year}/{month-1}
    (IRI's month param = current month − 1, the model initialization month)
    """
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month
    month_param = month - 1 if month > 1 else 12
    year_param  = year     if month > 1 else year - 1

    url = f"https://ensoforecast.iri.columbia.edu/strength_plot/{year_param}/{month_param}"
    print(f"Fetching IRI strength plot ({url}) ...")
    raw = _fetch_bytes(url)
    if not raw:
        return None

    try:
        fig = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  [WARN] Could not parse strength plot JSON: {exc}")
        return None

    seasons = []
    traces  = []
    for i, trace in enumerate(fig.get("data", [])):
        x = list(trace.get("x", []))
        if not seasons and x:
            seasons = x

        y_raw = trace.get("y", [])
        if isinstance(y_raw, dict) and "bdata" in y_raw:
            y = _decode_bdata(y_raw["bdata"], y_raw.get("dtype", "i1"))
        elif isinstance(y_raw, list):
            y = y_raw
        else:
            y = []

        plotly_color = trace.get("marker", {}).get("color", "")
        color = STRENGTH_COLORS[i] if i < len(STRENGTH_COLORS) else plotly_color
        traces.append({"name": trace.get("name", ""), "y": y, "color": color})

    # Back-calculate model counts per season from percentage values
    n_seasons = len(seasons)
    model_counts = []
    for si in range(n_seasons):
        season_pcts = [t["y"][si] for t in traces if si < len(t["y"])]
        model_counts.append(_find_model_count(season_pcts))

    layout = fig.get("layout", {})
    title  = layout.get("title", "")
    if isinstance(title, dict):
        title = title.get("text", "")

    return {
        "seasons":      seasons,
        "traces":       traces,
        "model_counts": model_counts,
        "title":        title,
        "year":         year_param,
        "month":        month_param,
    }


def get_iri_image_urls() -> dict:
    """
    Build IRI / CPC forecast image URLs for the current issuance month.
    IRI publishes figures mid-month; SST/strength endpoints use month − 1.
    """
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month

    sst_month = month - 1 if month > 1 else 12
    sst_year  = year      if month > 1 else year - 1

    return {
        "cpc_probs": (
            f"https://cpc.ncep.noaa.gov/archives/enso/roni/images/{year}/"
            f"enso-probs-{month:02d}{year}.png"
        ),
        "iri_sst_history": (
            f"https://iri.columbia.edu/wp-content/uploads/"
            f"{year}/{month:02d}/figure2.png"
        ),
        "iri_probs": (
            f"https://iri.columbia.edu/wp-content/uploads/"
            f"{year}/{month:02d}/figure3.png"
        ),
        "sst_plume": (
            f"https://ensoforecast.iri.columbia.edu/cgi-bin/"
            f"sst_table_img?month={sst_month}&year={sst_year}"
        ),
    }


if __name__ == "__main__":
    sp = fetch_strength_plot()
    if sp:
        print(f"\nTitle: {sp['title']}")
        print(f"Seasons: {sp['seasons']}")
        for t in sp["traces"]:
            print(f"  {t['name']}: {t['y']}")

    print("\nIRI Image URLs:")
    for k, v in get_iri_image_urls().items():
        print(f"  {k}: {v}")
