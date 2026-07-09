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


def _url_exists(url: str, timeout: int = 10) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "ENSOTracker/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year, month - 1) if month > 1 else (year - 1, 12)


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


_STRENGTH_CATEGORIES = [
    ("Very Strong La Niña", None, -2.0),
    ("Strong La Niña",      -2.0, -1.5),
    ("Moderate La Niña",    -1.5, -1.0),
    ("Weak La Niña",        -1.0, -0.5),
    ("Neutral",             -0.5,  0.5),
    ("Weak El Niño",         0.5,  1.0),
    ("Moderate El Niño",     1.0,  1.5),
    ("Strong El Niño",       1.5,  2.0),
    ("Very Strong El Niño",  2.0, None),
]

# Canonical season order for sorting forecast seasons
_SEASON_ORDER = ["DJF","JFM","FMA","MJJ","JJA","JAS","ASO","SON","OND","NDJ"]


_EXCLUDE_SERIES = {"AVG", "RELATIVE", "OBS", "Observed"}


def _is_forecast_model(name: str) -> bool:
    """Exclude observed data, ensemble averages, and relative-anomaly series."""
    return not any(tag in name for tag in _EXCLUDE_SERIES)


def compute_strength_from_predictions(predictions: list) -> Optional[dict]:
    """
    Derive ENSO strength category percentages from iri_model_predictions.

    Steps:
      1. Drop non-forecast series (OBS-*, DYN/STAT/REL AVG, RELATIVE).
      2. Average ensemble members within each model centre → one value per model per season.
      3. Classify each model mean into one of 9 strength bins.
      4. Compute % per bin per season.

    Returns the same dict structure as fetch_strength_plot() (JSON path).
    """
    if not predictions:
        return None

    from collections import defaultdict

    # Step 1+2: ensemble mean per (model, season), forecast models only.
    # Each modelling centre gets one vote regardless of how many ensemble members
    # they submitted — prevents UKMO (10 members) from having 10× the weight of XRO (1 member).
    raw: dict = defaultdict(list)
    for rec in predictions:
        name   = rec.get("model", "")
        season = rec.get("season", "")
        val    = rec.get("nino34_anomaly")
        if val is None or "OBS" in season or not _is_forecast_model(name):
            continue
        raw[(name, season)].append(float(val))

    model_season_mean = {k: sum(v) / len(v) for k, v in raw.items()}

    if not model_season_mean:
        return None

    # Determine the first upcoming season based on current month,
    # then rotate _SEASON_ORDER so the chart reads chronologically from now.
    _MONTH_TO_START = {
        1: "MJJ", 2: "MJJ", 3: "MJJ", 4: "JJA",
        5: "JAS", 6: "MJJ", 7: "JAS", 8: "ASO",
        9: "SON", 10: "OND", 11: "NDJ", 12: "DJF",
    }
    start = _MONTH_TO_START[datetime.now(timezone.utc).month]
    si    = _SEASON_ORDER.index(start) if start in _SEASON_ORDER else 0
    rotated_order = _SEASON_ORDER[si:] + _SEASON_ORDER[:si]

    avail = {s for (_, s) in model_season_mean}
    seasons = [s for s in rotated_order if s in avail]

    traces       = []
    model_counts = []
    for i, (name, lo, hi) in enumerate(_STRENGTH_CATEGORIES):
        y = []
        for si, season in enumerate(seasons):
            vals = [v for (_, s), v in model_season_mean.items() if s == season]
            n    = len(vals)
            cnt  = sum(1 for v in vals
                       if (lo is None or v >= lo) and (hi is None or v < hi))
            y.append(round(100 * cnt / n) if n else 0)
            if i == 0:
                model_counts.append(n)
        traces.append({"name": name, "y": y, "color": STRENGTH_COLORS[i]})

    return {
        "seasons":      seasons,
        "traces":       traces,
        "model_counts": model_counts,
        "title":        "ENSO Strength Categories",
    }


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
    URL = ("https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/"
           "?enso_tab=enso-sst_table")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page()
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            print(f"  Page title: {page.title()!r}  URL: {page.url!r}")

            # Explicitly click the SST table tab in case URL param isn't honoured headlessly
            for selector in ['a[href*="sst_table"]', '[data-tab="enso-sst_table"]',
                              '#enso-sst_table', 'a:has-text("SST")']:
                try:
                    page.click(selector, timeout=3000)
                    print(f"  Clicked tab selector: {selector!r}")
                    break
                except Exception:
                    pass

            try:
                page.wait_for_function(
                    "typeof Highcharts !== 'undefined' && Highcharts.charts.filter(Boolean).length > 0",
                    timeout=30000,
                )
                n_charts = page.evaluate("Highcharts.charts.filter(Boolean).length")
                print(f"  Highcharts ready — {n_charts} chart(s) found")
            except Exception as e:
                hc_defined = page.evaluate("typeof Highcharts !== 'undefined'")
                print(f"  [WARN] Highcharts wait failed: {e}")
                print(f"  Highcharts defined on page: {hc_defined}")
                page.screenshot(path="iri_debug.png", full_page=True)
                print("  Screenshot saved → iri_debug.png")

            page.wait_for_timeout(2000)
            records = page.evaluate("""
            () => {
                // Seasons present on the IRI Model Predictions plume chart.
                // MAM-OBS / May-OBS are the most-recent observed points;
                // MJJ onward are forecast seasons.
                // MAM and AMJ are never shown as standalone forecast labels on this chart.
                const SEASONS = new Set([
                    'MAM-OBS','May-OBS',
                    'MJJ','JJA','JAS','ASO','SON','OND','NDJ','DJF','JFM','FMA'
                ]);
                const out = [];
                if (typeof Highcharts === 'undefined') return out;

                // Target only the Model Predictions chart via its known div ID.
                // Fall back to scanning all category-axis charts if the div is absent.
                const container = document.getElementById('figure4_highchart');
                let charts = [];
                if (container) {
                    const idx = parseInt(container.getAttribute('data-highcharts-chart'));
                    const c = Highcharts.charts[idx];
                    if (c) charts = [c];
                }
                if (!charts.length) {
                    charts = Highcharts.charts.filter(
                        c => c && c.xAxis[0] && c.xAxis[0].categories
                    );
                }

                charts.forEach(chart => {
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
    Fetch ENSO strength categories from IRI's endpoint.
    IRI previously returned Plotly JSON; as of mid-2026 the endpoint returns
    an SVG image instead. We detect which format is served and handle both:
      - SVG  → return {"svg_url": url, "year": y, "month": m}
      - JSON → parse traces and return the full dict (legacy path)
    Falls back to month-2 if the current month isn't published yet.
    """
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month

    raw = None
    url_used = None
    year_param, month_param = None, None
    for offset in (1, 2):
        y, m = _prev_month(year, month) if offset == 1 else _prev_month(*_prev_month(year, month))
        url = f"https://ensoforecast.iri.columbia.edu/strength_plot/{y}/{m}"
        print(f"Fetching IRI strength plot ({url}) ...")
        raw = _fetch_bytes(url)
        if raw:
            year_param, month_param, url_used = y, m, url
            break

    if not raw:
        return None

    # IRI now serves SVG — display directly as an image
    if raw.lstrip()[:5] in (b"<?xml", b"<svg "):
        print(f"  IRI strength plot is SVG — will embed as image")
        return {"svg_url": url_used, "year": year_param, "month": month_param}

    # Legacy: Plotly JSON path (kept in case IRI reverts)
    try:
        fig = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  [WARN] Could not parse strength plot response: {exc}")
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
        "seasons": seasons, "traces": traces,
        "model_counts": model_counts, "title": title,
        "year": year_param, "month": month_param,
    }


def get_iri_image_urls() -> dict:
    """
    Build IRI / CPC forecast image URLs.
    Checks whether the current month's figures are published; falls back to
    the previous month if not (IRI typically publishes mid-month).
    """
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month

    # Determine which month's figures are actually available
    fig_year, fig_month = year, month
    test_url = (f"https://iri.columbia.edu/wp-content/uploads/"
                f"{fig_year}/{fig_month:02d}/figure2.png")
    if not _url_exists(test_url):
        fig_year, fig_month = _prev_month(year, month)
        print(f"  [INFO] IRI figures not yet published for {year}/{month:02d} "
              f"— using {fig_year}/{fig_month:02d}")

    sst_year, sst_month = _prev_month(fig_year, fig_month)

    return {
        "cpc_probs": (
            f"https://cpc.ncep.noaa.gov/archives/enso/roni/images/{fig_year}/"
            f"enso-probs-{fig_month:02d}{fig_year}.png"
        ),
        "iri_sst_history": (
            f"https://iri.columbia.edu/wp-content/uploads/"
            f"{fig_year}/{fig_month:02d}/figure2.png"
        ),
        "iri_probs": (
            f"https://iri.columbia.edu/wp-content/uploads/"
            f"{fig_year}/{fig_month:02d}/figure3.png"
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
