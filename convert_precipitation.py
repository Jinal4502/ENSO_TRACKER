"""
convert_precipitation.py  —  LOCAL USE ONLY
Reads nclimgrid_prcp.nc and writes:
  docs/data/usa_monthly_grid.csv  — Gaussian-smoothed 1.0° grid, all 48 CONUS states
  docs/data/usa_meta.json         — metadata

Run locally after downloading a fresh NClimGrid NetCDF, then commit both files to GitHub.
The CSV is loaded at browser runtime; CI does not regenerate it (no NetCDF on CI).
"""

import csv
import json
import numpy as np
from pathlib import Path
from typing import Optional

PRCP_FILE   = Path("nclimgrid_prcp.nc")
OUT_GRID    = 1.0      # output resolution in degrees (0.25° → 1.0°)
GAUSS_SIGMA = 1.0      # Gaussian smoothing sigma in output-grid cells
YEAR_START  = 1970

# Full CONUS bounding box
USA_LAT_MIN, USA_LAT_MAX = 24.0, 50.0
USA_LON_MIN, USA_LON_MAX = -125.0, -66.0

DATA_DIR  = Path("docs/data")
CSV_GRID  = DATA_DIR / "usa_monthly_grid.csv"
META_FILE = DATA_DIR / "usa_meta.json"

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]

# State bounding boxes — priority order (smaller/more specific first).
# First match wins, so overlapping boxes resolve to the earlier entry.
STATE_BOUNDS = [
    # New England (tiny states first)
    ("RI",  41.1, 42.1, -71.9, -71.1),
    ("CT",  40.9, 42.1, -73.8, -71.7),
    ("MA",  41.2, 42.9, -73.5, -69.9),
    ("NH",  42.7, 45.3, -72.6, -70.6),
    ("VT",  42.7, 45.0, -73.5, -71.5),
    ("ME",  43.0, 47.5, -71.1, -67.0),
    # Mid-Atlantic
    ("DE",  38.4, 39.9, -75.8, -75.0),
    ("MD",  37.9, 39.7, -79.5, -75.1),
    ("NJ",  38.9, 41.4, -75.6, -73.9),
    ("PA",  39.7, 42.3, -80.5, -74.7),
    ("NY",  40.5, 45.1, -79.8, -71.9),
    # South Atlantic
    ("WV",  37.2, 40.6, -82.7, -77.7),
    ("VA",  36.5, 39.5, -83.7, -75.2),
    ("NC",  33.8, 36.6, -84.4, -75.4),
    ("SC",  32.0, 35.2, -83.4, -78.5),
    ("GA",  30.4, 35.0, -85.6, -80.8),
    ("FL",  24.5, 31.0, -87.7, -79.9),
    # East South Central
    ("KY",  36.5, 39.2, -89.6, -81.9),
    ("TN",  34.9, 36.7, -90.3, -81.6),
    ("AL",  30.2, 35.0, -88.5, -84.9),
    ("MS",  30.2, 35.0, -91.7, -88.1),
    # West South Central
    ("AR",  33.0, 36.5, -94.6, -89.7),
    ("LA",  28.9, 33.1, -94.1, -88.8),
    ("OK",  33.6, 37.0, -103.1, -94.4),
    ("TX",  25.8, 36.5, -106.7, -93.5),
    # East North Central
    ("OH",  38.4, 42.4, -84.8, -80.5),
    ("IN",  37.8, 41.8, -88.1, -84.8),
    ("IL",  36.9, 42.5, -91.5, -87.5),
    ("MI",  41.7, 48.4, -90.5, -82.4),
    ("WI",  42.5, 47.1, -92.9, -86.8),
    # West North Central
    ("MN",  43.5, 49.5, -97.3, -89.5),
    ("IA",  40.4, 43.5, -96.7, -90.1),
    ("MO",  36.0, 40.6, -95.8, -89.1),
    ("ND",  45.9, 49.1, -104.2, -96.6),
    ("SD",  42.5, 46.0, -104.2, -96.4),
    ("NE",  40.0, 43.0, -104.1, -95.3),
    ("KS",  37.0, 40.1, -102.1, -94.6),
    # Mountain
    ("MT",  44.4, 49.1, -116.1, -104.0),
    ("ID",  42.0, 49.1, -117.3, -111.0),
    ("WY",  41.0, 45.0, -111.1, -104.1),
    ("CO",  37.0, 41.1, -109.1, -102.0),
    ("NM",  31.3, 37.0, -109.1, -103.0),
    ("AZ",  31.3, 37.0, -114.9, -109.0),
    ("UT",  37.0, 42.1, -114.2, -109.0),
    ("NV",  35.0, 42.1, -120.1, -114.0),
    # Pacific
    ("WA",  45.5, 49.1, -124.8, -116.9),
    ("OR",  42.0, 46.3, -124.7, -116.5),
    ("CA",  32.5, 42.1, -124.6, -114.1),
]


def assign_state(lat: float, lon: float) -> Optional[str]:
    for name, lat_min, lat_max, lon_min, lon_max in STATE_BOUNDS:
        if lat_min <= lat < lat_max and lon_min <= lon < lon_max:
            return name
    return None


def convert_precipitation_data() -> dict:
    try:
        import netCDF4 as nc
        from netCDF4 import num2date
        from scipy.ndimage import gaussian_filter
    except ImportError as e:
        raise RuntimeError(f"Missing dependency: {e}. pip install netCDF4 scipy")

    if not PRCP_FILE.exists():
        raise FileNotFoundError(
            f"{PRCP_FILE} not found.\n"
            "Download NClimGrid-Monthly from:\n"
            "  https://www.ncei.noaa.gov/products/land-based-station/nclimgrid-monthly"
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading NClimGrid precipitation ...")
    ds    = nc.Dataset(PRCP_FILE)
    lat   = np.array(ds.variables["lat"][:])
    lon   = np.array(ds.variables["lon"][:])
    times = ds.variables["time"][:]
    dates = num2date(times, ds.variables["time"].units)

    # Extract full CONUS region at native 0.25° resolution
    lat_idx = np.where((lat >= USA_LAT_MIN) & (lat <= USA_LAT_MAX))[0]
    lon_idx = np.where((lon >= USA_LON_MIN) & (lon <= USA_LON_MAX))[0]
    sub_lat = lat[lat_idx]
    sub_lon = lon[lon_idx]

    time_idx  = np.array([i for i, d in enumerate(dates) if int(d.year) >= YEAR_START])
    dates_sub = [dates[i] for i in time_idx]
    T         = len(time_idx)

    print(f"  Reading CONUS region: {len(lat_idx)} lat × {len(lon_idx)} lon, "
          f"{T} months from {YEAR_START} ...")
    raw = np.array(
        ds.variables["prcp"][time_idx[0]:time_idx[-1]+1,
                             lat_idx[0]:lat_idx[-1]+1,
                             lon_idx[0]:lon_idx[-1]+1],
        dtype=float,
    )
    fill = float(getattr(ds.variables["prcp"], "_FillValue", -9999.0))
    raw[raw == fill] = np.nan
    raw[raw < 0]     = np.nan
    ds.close()
    print(f"  Raw shape: {raw.shape}  "
          f"(NaN: {100*np.isnan(raw[0]).mean():.0f}% in first month)")

    years_arr  = np.array([int(d.year)  for d in dates_sub])
    months_arr = np.array([int(d.month) for d in dates_sub])

    # ENSO classification per (year, month)
    try:
        from fetch_hurricanes import fetch_oni_classifications
        _, month_class = fetch_oni_classifications()
    except Exception:
        month_class = {}

    # ── Build 1.0° output grid ────────────────────────────────────────────
    out_lats    = np.arange(USA_LAT_MIN, USA_LAT_MAX, OUT_GRID)
    out_lons    = np.arange(USA_LON_MIN, USA_LON_MAX, OUT_GRID)
    centres_lat = out_lats + OUT_GRID / 2
    centres_lon = out_lons + OUT_GRID / 2
    n_lat, n_lon = len(out_lats), len(out_lons)

    # Pre-assign state to each output cell centre
    cell_state: dict = {}
    for bi, rlat in enumerate(centres_lat):
        for bj, rlon in enumerate(centres_lon):
            s = assign_state(float(rlat), float(rlon))
            if s:
                cell_state[(bi, bj)] = s

    print(f"  Output grid: {n_lat}×{n_lon} bins, {len(cell_state)} CONUS cells at {OUT_GRID}°")

    # ── Aggregate 0.25° → 1.0° ───────────────────────────────────────────
    lat_bins = np.digitize(sub_lat, out_lats) - 1
    lon_bins = np.digitize(sub_lon, out_lons) - 1

    prcp_coarse = np.full((T, n_lat, n_lon), np.nan)
    print("  Aggregating 0.25° → 1.0° ...")
    for bi in range(n_lat):
        li = lat_bins == bi
        if not li.any():
            continue
        for bj in range(n_lon):
            if (bi, bj) not in cell_state:
                continue
            lj = lon_bins == bj
            if not lj.any():
                continue
            cell  = raw[:, li, :][:, :, lj]
            flat  = cell.reshape(T, -1)
            valid = ~np.isnan(flat)
            cnt   = valid.sum(axis=1)
            sums  = np.where(valid, flat, 0.0).sum(axis=1)
            with np.errstate(invalid="ignore", divide="ignore"):
                prcp_coarse[:, bi, bj] = np.where(cnt > 0, sums / cnt, np.nan)

    # ── NaN-aware Gaussian smoothing per time step ────────────────────────
    print(f"  Applying Gaussian smoothing (σ={GAUSS_SIGMA} cell = {GAUSS_SIGMA*OUT_GRID}°) ...")
    prcp_smooth = np.full_like(prcp_coarse, np.nan)
    for t in range(T):
        field    = prcp_coarse[t]
        nan_mask = np.isnan(field)
        filled   = np.where(nan_mask, 0.0, field)
        weight   = (~nan_mask).astype(float)
        sm_num   = gaussian_filter(filled, sigma=GAUSS_SIGMA)
        sm_den   = gaussian_filter(weight, sigma=GAUSS_SIGMA)
        with np.errstate(invalid="ignore", divide="ignore"):
            prcp_smooth[t] = np.where(sm_den > 0.1, sm_num / sm_den, np.nan)

    # ── Write usa_monthly_grid.csv ────────────────────────────────────────
    print(f"  Writing {CSV_GRID} ...")
    with open(CSV_GRID, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "month", "lat", "lon", "prcp_mm", "enso", "state"])
        for t in range(T):
            year  = years_arr[t]
            month = months_arr[t]
            enso  = month_class.get((year, month), "Neutral")
            for (bi, bj), state in sorted(cell_state.items()):
                v = prcp_smooth[t, bi, bj]
                if not np.isnan(v):
                    w.writerow([
                        year, month,
                        round(float(centres_lat[bi]), 4),
                        round(float(centres_lon[bj]), 4),
                        round(float(v), 1),
                        enso, state,
                    ])

    first = f"{years_arr[0]}-{months_arr[0]:02d}"
    last  = f"{years_arr[-1]}-{months_arr[-1]:02d}"
    meta  = {
        "first_month": first,
        "last_month":  last,
        "n_months":    T,
        "n_cells":     len(cell_state),
        "grid_deg":    OUT_GRID,
        "smoothing":   f"gaussian_sigma{GAUSS_SIGMA}",
        "states":      sorted(set(cell_state.values())),
    }
    with open(META_FILE, "w") as f:
        json.dump(meta, f, indent=2)

    sz = CSV_GRID.stat().st_size // (1024 * 1024)
    print(f"  Done — {T} months, {len(cell_state)} cells, {first}→{last}  "
          f"(grid CSV: {sz} MB)")
    return meta


if __name__ == "__main__":
    meta = convert_precipitation_data()
    print(f"\n{meta['n_cells']} cells at {meta['grid_deg']}°  "
          f"({meta['first_month']} → {meta['last_month']})")
