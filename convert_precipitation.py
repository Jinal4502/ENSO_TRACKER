"""
convert_precipitation.py  —  LOCAL USE ONLY
Reads nclimgrid_prcp.nc and writes:
  docs/data/sw_monthly_grid.csv  — Gaussian-smoothed 0.5° grid, 7 SW states
  docs/data/sw_meta.json         — metadata

Run locally after downloading a fresh NClimGrid NetCDF, then commit both files to GitHub.
The CSV is loaded at browser runtime; CI does not regenerate it (no NetCDF on CI).
"""

import csv
import json
import numpy as np
from pathlib import Path
from typing import Optional

PRCP_FILE   = Path("nclimgrid_prcp.nc")
OUT_GRID    = 0.5      # output resolution in degrees
GAUSS_SIGMA = 1.0      # Gaussian smoothing sigma in output-grid cells
YEAR_START  = 1970

# Full bounding box covering all 7 SW states
SW_LAT_MIN, SW_LAT_MAX = 25.5, 42.0
SW_LON_MIN, SW_LON_MAX = -124.5, -93.5

DATA_DIR  = Path("docs/data")
CSV_GRID  = DATA_DIR / "sw_monthly_grid.csv"
META_FILE = DATA_DIR / "sw_meta.json"

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]

# State bounding boxes checked in priority order — first match wins.
# Four Corners states (AZ/NM/UT/CO) share clean borders at 37°N and 109°W.
# NV is listed before CA so NV wins the 35-42°N, -120 to -114°W overlap zone.
STATE_BOUNDS = [
    ("AZ", 31.0, 37.0, -115.0, -109.0),
    ("NM", 31.0, 37.0, -109.0, -102.5),
    ("CO", 37.0, 41.5, -109.0, -102.0),
    ("UT", 37.0, 42.0, -114.0, -109.0),
    ("NV", 35.0, 42.0, -120.0, -114.0),
    ("CA", 32.0, 42.0, -124.5, -114.0),
    ("TX", 25.5, 36.5, -107.0,  -93.5),
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

    # Extract full SW region at native 0.25° resolution
    lat_idx = np.where((lat >= SW_LAT_MIN) & (lat <= SW_LAT_MAX))[0]
    lon_idx = np.where((lon >= SW_LON_MIN) & (lon <= SW_LON_MAX))[0]
    sub_lat = lat[lat_idx]
    sub_lon = lon[lon_idx]

    time_idx  = np.array([i for i, d in enumerate(dates) if int(d.year) >= YEAR_START])
    dates_sub = [dates[i] for i in time_idx]
    T         = len(time_idx)

    print(f"  Reading SW region: {len(lat_idx)} lat × {len(lon_idx)} lon, "
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

    # ── Build 0.5° output grid ────────────────────────────────────────────
    out_lats    = np.arange(SW_LAT_MIN, SW_LAT_MAX, OUT_GRID)
    out_lons    = np.arange(SW_LON_MIN, SW_LON_MAX, OUT_GRID)
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

    print(f"  Output grid: {n_lat}×{n_lon} bins, {len(cell_state)} SW cells at {OUT_GRID}°")

    # ── Aggregate 0.25° → 0.5° ───────────────────────────────────────────
    lat_bins = np.digitize(sub_lat, out_lats) - 1
    lon_bins = np.digitize(sub_lon, out_lons) - 1

    prcp_coarse = np.full((T, n_lat, n_lon), np.nan)
    print("  Aggregating 0.25° → 0.5° ...")
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
    # Normalised convolution: smooth numerator and denominator separately
    # so land-boundary NaNs don't bleed into valid cells.
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

    # ── Write sw_monthly_grid.csv ─────────────────────────────────────────
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
