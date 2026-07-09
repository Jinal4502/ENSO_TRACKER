"""
convert_precipitation.py  —  LOCAL USE ONLY
Reads nclimgrid_prcp.nc (1.4 GB, not committed to git) and writes three CSVs
plus az_meta.json to docs/data/.  Run this once whenever you download a fresh
NetCDF, then commit the CSVs + az_meta.json to GitHub.

Usage:
    python convert_precipitation.py
"""

import csv
import json
import numpy as np
from pathlib import Path

PRCP_FILE  = Path("nclimgrid_prcp.nc")
GRID_DEG   = 0.25
YEAR_START = 1970

AZ_LAT_MIN, AZ_LAT_MAX = 31.0, 37.0
AZ_LON_MIN, AZ_LON_MAX = -115.0, -109.0

DATA_DIR   = Path("docs/data")
CSV_GRID   = DATA_DIR / "az_monthly_grid.csv"
CSV_ANNUAL = DATA_DIR / "az_annual.csv"
CSV_CLIM   = DATA_DIR / "az_climatology.csv"
META_FILE  = DATA_DIR / "az_meta.json"

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]


def convert_precipitation_data() -> dict:
    try:
        import netCDF4 as nc
        from netCDF4 import num2date
    except ImportError:
        raise RuntimeError("netCDF4 is required: pip install netCDF4")

    if not PRCP_FILE.exists():
        raise FileNotFoundError(
            f"{PRCP_FILE} not found.\n"
            "Download NClimGrid from https://www.ncei.noaa.gov/products/"
            "land-based-station/nclimgrid-monthly and place it here."
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading NClimGrid precipitation ...")
    ds = nc.Dataset(PRCP_FILE)

    lat   = np.array(ds.variables["lat"][:])
    lon   = np.array(ds.variables["lon"][:])
    times = ds.variables["time"][:]
    dates = num2date(times, ds.variables["time"].units)

    lat_idx = np.where((lat >= AZ_LAT_MIN) & (lat <= AZ_LAT_MAX))[0]
    lon_idx = np.where((lon >= AZ_LON_MIN) & (lon <= AZ_LON_MAX))[0]
    sub_lat = lat[lat_idx]
    sub_lon = lon[lon_idx]

    time_idx  = np.array([i for i, d in enumerate(dates) if int(d.year) >= YEAR_START])
    dates_sub = [dates[i] for i in time_idx]

    print(f"  Reading AZ sub-region: {len(lat_idx)} lat × {len(lon_idx)} lon, "
          f"{len(time_idx)} months from {YEAR_START} ...")
    raw = np.array(
        ds.variables["prcp"][time_idx[0]:time_idx[-1]+1,
                             lat_idx[0]:lat_idx[-1]+1,
                             lon_idx[0]:lon_idx[-1]+1],
        dtype=float
    )
    fill = float(getattr(ds.variables["prcp"], "_FillValue", -9999.0))
    raw[raw == fill] = np.nan
    raw[raw < 0]     = np.nan
    ds.close()
    print(f"  Raw shape: {raw.shape}  "
          f"(NaN: {100*np.isnan(raw[0]).mean():.0f}% in first month)")

    # 0.25° bin edges and centres
    out_lats    = np.arange(AZ_LAT_MIN, AZ_LAT_MAX, GRID_DEG)
    out_lons    = np.arange(AZ_LON_MIN, AZ_LON_MAX, GRID_DEG)
    n_lat, n_lon = len(out_lats), len(out_lons)
    centres_lat  = out_lats + GRID_DEG / 2
    centres_lon  = out_lons + GRID_DEG / 2

    lat_bins = np.digitize(sub_lat, out_lats) - 1
    lon_bins = np.digitize(sub_lon, out_lons) - 1

    T    = raw.shape[0]
    prcp = np.full((T, n_lat, n_lon), np.nan)

    print(f"  Aggregating to {n_lat}×{n_lon} = {n_lat*n_lon} bins at {GRID_DEG}° ...")
    for bi in range(n_lat):
        li = lat_bins == bi
        if not li.any():
            continue
        for bj in range(n_lon):
            lj = lon_bins == bj
            if not lj.any():
                continue
            cell  = raw[:, li, :][:, :, lj]
            flat  = cell.reshape(T, -1)
            valid = ~np.isnan(flat)
            cnt   = valid.sum(axis=1)
            sums  = np.where(valid, flat, 0.0).sum(axis=1)
            with np.errstate(invalid="ignore", divide="ignore"):
                prcp[:, bi, bj] = np.where(cnt > 0, sums / cnt, np.nan)

    years_arr  = np.array([int(d.year)  for d in dates_sub])
    months_arr = np.array([int(d.month) for d in dates_sub])

    try:
        from fetch_hurricanes import fetch_oni_classifications
        _, month_class = fetch_oni_classifications()
    except Exception:
        month_class = {}

    # ── CSV 1: az_monthly_grid.csv ─────────────────────────────────────────
    print(f"  Writing {CSV_GRID} ...")
    with open(CSV_GRID, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "month", "lat", "lon", "prcp_mm", "enso"])
        for t in range(T):
            year  = years_arr[t]
            month = months_arr[t]
            enso  = month_class.get((year, month), "Neutral")
            for bi, rlat in enumerate(centres_lat):
                for bj, rlon in enumerate(centres_lon):
                    v = prcp[t, bi, bj]
                    if not np.isnan(v):
                        w.writerow([year, month,
                                    round(float(rlat), 4),
                                    round(float(rlon), 4),
                                    round(float(v), 1),
                                    enso])

    # ── CSV 2: az_annual.csv ───────────────────────────────────────────────
    unique_years = sorted(set(int(y) for y in years_arr))
    print(f"  Writing {CSV_ANNUAL} ...")
    with open(CSV_ANNUAL, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "total_mm", "enso"])
        for year in unique_years:
            mask = years_arr == year
            vals = [float(np.nanmean(prcp[i]))
                    for i in np.where(mask)[0]
                    if not np.all(np.isnan(prcp[i]))]
            total = round(sum(vals), 1) if vals else 0.0
            enso  = month_class.get((year, 9), "Neutral")
            w.writerow([year, total, enso])

    # ── CSV 3: az_climatology.csv ──────────────────────────────────────────
    print(f"  Writing {CSV_CLIM} ...")
    with open(CSV_CLIM, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "month_name", "avg_mm"])
        for m in range(1, 13):
            mask = months_arr == m
            avg  = float(np.nanmean(prcp[mask]))
            w.writerow([m, MONTH_NAMES[m - 1], round(avg, 2)])

    first = f"{years_arr[0]}-{months_arr[0]:02d}"
    last  = f"{years_arr[-1]}-{months_arr[-1]:02d}"

    meta = {
        "first_month": first,
        "last_month":  last,
        "n_months":    T,
        "n_cells":     n_lat * n_lon,
        "grid_deg":    GRID_DEG,
    }

    # ── az_meta.json — read by fetch_precipitation.py (runs in CI too) ─────
    print(f"  Writing {META_FILE} ...")
    with open(META_FILE, "w") as f:
        json.dump(meta, f, indent=2)

    sz = CSV_GRID.stat().st_size // (1024 * 1024)
    print(f"  Done — {T} months, {n_lat*n_lon} cells, {first}→{last}  "
          f"(grid CSV: {sz} MB)")
    return meta


if __name__ == "__main__":
    meta = convert_precipitation_data()
    print(f"\n{meta['n_cells']} cells at {meta['grid_deg']}°  "
          f"({meta['first_month']} → {meta['last_month']})")
