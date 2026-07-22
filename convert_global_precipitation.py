"""
convert_global_precipitation.py  —  LOCAL USE ONLY
Reads GPCC Full Data Monthly (0.5°) and writes per-region CSV + JSON files
used by the global precipitation page.

Place the downloaded file as precip.mon.total.v7.nc in this directory, then:
  python convert_global_precipitation.py

Download from:
  https://downloads.psl.noaa.gov/Datasets/gpcc/full_v7/precip.mon.total.v7.nc

Outputs docs/data/{region}_monthly_grid.csv and docs/data/{region}_meta.json
for each region defined in REGIONS below.  Commit those files to GitHub;
CI does not regenerate them (no NetCDF on CI).
"""

import csv
import json
from pathlib import Path
from typing import Optional, List, Tuple
import numpy as np

# Accepted filenames in priority order
GPCC_CANDIDATES = [
    Path("precip.mon.total.v7.nc"),
    Path("gpcc_precip_2.5.nc"),
    Path("gpcc_precip.nc"),
]
DATA_DIR   = Path("docs/data")
YEAR_START = 1970
GAUSS_SIGMA = 1.0   # smoothing applied at native 0.5° resolution
OUT_GRID    = 1.0   # aggregate 0.5° → 1.0° to keep CSV files ≤ 15 MB

# ── Region definitions ────────────────────────────────────────────────────────
# subregions: list of (label, lat_min, lat_max, lon_min, lon_max)
# Priority order: first match wins for each cell centre.
REGIONS = {
    "india": {
        "name": "India",
        "lat_min": 5.0, "lat_max": 38.0,
        "lon_min": 67.0, "lon_max": 98.0,
        "subregions": [
            ("Northeast",   22.0, 30.0, 85.0, 98.0),
            ("North",       28.0, 38.0, 67.0, 85.0),
            ("West Coast",   8.0, 22.0, 67.0, 77.0),
            ("Central",     17.0, 28.0, 77.0, 86.0),
            ("South",        5.0, 17.0, 74.0, 85.0),
        ],
    },
    "australia": {
        "name": "Australia",
        "lat_min": -45.0, "lat_max": -9.0,
        "lon_min": 112.0, "lon_max": 155.0,
        "subregions": [
            ("Northern",  -22.0,  -9.0, 112.0, 155.0),
            ("Queensland",-28.0, -15.0, 138.0, 155.0),
            ("NSW-Vic",   -39.0, -28.0, 140.0, 155.0),
            ("Western",   -39.0, -22.0, 112.0, 125.0),
            ("South",     -39.0, -28.0, 125.0, 140.0),
        ],
    },
    "brazil": {
        "name": "Brazil",
        "lat_min": -34.0, "lat_max": 6.0,
        "lon_min": -74.0, "lon_max": -34.0,
        "subregions": [
            ("Amazon",    -5.0,  6.0, -74.0, -47.0),
            ("Northeast",-15.0,  0.0, -47.0, -34.0),
            ("Central",  -20.0, -5.0, -60.0, -47.0),
            ("Southeast",-26.0,-14.0, -50.0, -38.0),
            ("South",    -34.0,-22.0, -57.0, -48.0),
        ],
    },
    "east_africa": {
        "name": "East Africa",
        "lat_min": -12.0, "lat_max": 18.0,
        "lon_min": 28.0, "lon_max": 52.0,
        "subregions": [
            ("Horn",           2.0, 18.0, 38.0, 52.0),
            ("Ethiopia",       3.0, 15.0, 33.0, 48.0),
            ("Kenya-Tanzania",-12.0,  5.0, 32.0, 42.0),
            ("Great Lakes",   -5.0,   5.0, 28.0, 38.0),
        ],
    },
}


def assign_subregion(lat: float, lon: float,
                     subregions: List[Tuple]) -> Optional[str]:
    for name, lat_min, lat_max, lon_min, lon_max in subregions:
        if lat_min <= lat < lat_max and lon_min <= lon < lon_max:
            return name
    return None


def convert_all_regions() -> None:
    try:
        import netCDF4 as nc
        from netCDF4 import num2date
        from scipy.ndimage import gaussian_filter
    except ImportError as e:
        raise RuntimeError(f"pip install netCDF4 scipy  ({e})")

    gpcc_file = next((p for p in GPCC_CANDIDATES if p.exists()), None)
    if gpcc_file is None:
        raise FileNotFoundError(
            "GPCC file not found. Download from:\n"
            "  https://downloads.psl.noaa.gov/Datasets/gpcc/full_v7/precip.mon.total.v7.nc\n"
            f"and place it as {GPCC_CANDIDATES[0]} in this directory.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Opening {gpcc_file} ...")
    ds = nc.Dataset(gpcc_file)

    # Detect precipitation variable name
    prcp_var = next((v for v in ("precip", "prcp", "precipitation", "pre", "p")
                     if v in ds.variables), None)
    if prcp_var is None:
        raise RuntimeError(f"Cannot find precip variable. Got: {list(ds.variables.keys())}")

    # Lat / lon — GPCC from PSL uses 0–360 longitude
    lat_raw = np.array(ds.variables["lat"][:])
    lon_raw = np.array(ds.variables["lon"][:])
    lon     = np.where(lon_raw > 180, lon_raw - 360, lon_raw)

    # Detect native grid resolution from lat spacing
    grid_deg = round(abs(float(lat_raw[1] - lat_raw[0])), 3)
    print(f"  Variable '{prcp_var}' · {grid_deg}° grid · "
          f"{len(lat_raw)} lat × {len(lon_raw)} lon")

    times  = ds.variables["time"][:]
    dates  = num2date(times, ds.variables["time"].units,
                      only_use_cftime_datetimes=False,
                      only_use_python_datetimes=True)

    time_idx  = [i for i, d in enumerate(dates) if d.year >= YEAR_START]
    dates_sub = [dates[i] for i in time_idx]
    T         = len(time_idx)
    years_arr  = np.array([d.year  for d in dates_sub])
    months_arr = np.array([d.month for d in dates_sub])
    print(f"  {T} months: {dates_sub[0].year}-{dates_sub[0].month:02d}"
          f" → {dates_sub[-1].year}-{dates_sub[-1].month:02d}")

    fill = float(getattr(ds.variables[prcp_var], "_FillValue", -9.96921e+36))

    # ENSO classification per (year, month)
    try:
        from fetch_hurricanes import fetch_oni_classifications
        _, month_class = fetch_oni_classifications()
    except Exception:
        month_class = {}

    for region_key, rcfg in REGIONS.items():
        print(f"\n── {rcfg['name']} ──")

        lat_min, lat_max = rcfg["lat_min"], rcfg["lat_max"]
        lon_min, lon_max = rcfg["lon_min"], rcfg["lon_max"]

        lat_idx  = np.where((lat_raw >= lat_min) & (lat_raw <= lat_max))[0]
        lon_mask = (lon >= lon_min) & (lon <= lon_max)
        lon_idx  = np.where(lon_mask)[0]

        sub_lat = lat_raw[lat_idx]
        sub_lon = lon[lon_idx]    # -180 to 180

        print(f"  Slice: {len(lat_idx)} lat × {len(lon_idx)} lon")

        # Read this region's data slice for all time steps
        t0, t1 = time_idx[0], time_idx[-1] + 1
        raw = np.array(
            ds.variables[prcp_var][t0:t1,
                                   lat_idx[0]:lat_idx[-1]+1,
                                   lon_idx[0]:lon_idx[-1]+1],
            dtype=float,
        )
        raw[np.abs(raw - fill) < 1e25] = np.nan
        raw[raw < 0] = np.nan

        # NaN-aware Gaussian smoothing (same approach as NClimGrid SW USA)
        print(f"  Applying Gaussian smoothing (σ={GAUSS_SIGMA} cell = {GAUSS_SIGMA*grid_deg:.2f}°) ...")
        prcp_smooth = np.full_like(raw, np.nan)
        for t in range(T):
            field    = raw[t]
            nan_mask = np.isnan(field)
            filled   = np.where(nan_mask, 0.0, field)
            weight   = (~nan_mask).astype(float)
            sm_num   = gaussian_filter(filled, sigma=GAUSS_SIGMA)
            sm_den   = gaussian_filter(weight, sigma=GAUSS_SIGMA)
            with np.errstate(invalid="ignore", divide="ignore"):
                prcp_smooth[t] = np.where(sm_den > 0.1, sm_num / sm_den, np.nan)

        # ── Aggregate 0.5° → 1.0° output grid ──────────────────────────────
        out_lats = np.arange(lat_min, lat_max, OUT_GRID)
        out_lons = np.arange(lon_min, lon_max, OUT_GRID)
        cen_lat  = out_lats + OUT_GRID / 2
        cen_lon  = out_lons + OUT_GRID / 2
        n_lat, n_lon = len(out_lats), len(out_lons)

        lat_bins = np.floor((sub_lat - lat_min) / OUT_GRID).astype(int)
        lon_bins = np.floor((sub_lon - lon_min) / OUT_GRID).astype(int)

        prcp_coarse = np.full((T, n_lat, n_lon), np.nan)
        for bi in range(n_lat):
            li_mask = lat_bins == bi
            if not li_mask.any():
                continue
            for bj in range(n_lon):
                lj_mask = lon_bins == bj
                if not lj_mask.any():
                    continue
                cell = prcp_smooth[:, li_mask, :][:, :, lj_mask].reshape(T, -1)
                valid = ~np.isnan(cell)
                cnt  = valid.sum(axis=1)
                sums = np.where(valid, cell, 0.0).sum(axis=1)
                with np.errstate(invalid="ignore", divide="ignore"):
                    prcp_coarse[:, bi, bj] = np.where(cnt > 0, sums / cnt, np.nan)

        # Assign subregion for each 1.0° output cell centre
        cell_info = {}   # (bi, bj) → (clat, clon, subregion)
        for bi, clat in enumerate(cen_lat):
            for bj, clon in enumerate(cen_lon):
                if np.all(np.isnan(prcp_coarse[:, bi, bj])):
                    continue   # ocean / no data
                sr = assign_subregion(float(clat), float(clon), rcfg["subregions"])
                if sr is not None:
                    cell_info[(bi, bj)] = (float(clat), float(clon), sr)

        print(f"  Output cells at {OUT_GRID}°: {len(cell_info)}")

        csv_path  = DATA_DIR / f"{region_key}_monthly_grid.csv"
        meta_path = DATA_DIR / f"{region_key}_meta.json"

        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["year", "month", "lat", "lon", "prcp_mm", "enso", "state"])
            for t in range(T):
                year  = int(years_arr[t])
                month = int(months_arr[t])
                enso  = month_class.get((year, month), "Neutral")
                for (bi, bj), (clat, clon, sr) in sorted(cell_info.items()):
                    v = prcp_coarse[t, bi, bj]
                    if not np.isnan(v):
                        w.writerow([year, month,
                                    round(clat, 2), round(clon, 2),
                                    round(float(v), 1), enso, sr])

        first = f"{int(years_arr[0])}-{int(months_arr[0]):02d}"
        last  = f"{int(years_arr[-1])}-{int(months_arr[-1]):02d}"
        subregion_names = sorted({v[2] for v in cell_info.values()})
        meta = {
            "region_key":  region_key,
            "region_name": rcfg["name"],
            "first_month": first,
            "last_month":  last,
            "n_months":    T,
            "n_cells":     len(cell_info),
            "grid_deg":    OUT_GRID,
            "smoothing":   f"gaussian_sigma{GAUSS_SIGMA}_then_aggregated_to_{OUT_GRID}deg",
            "states":      subregion_names,
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        sz = csv_path.stat().st_size // (1024 * 1024)
        print(f"  → {csv_path.name} ({sz} MB)   {meta_path.name}")

    ds.close()
    print("\nDone. Commit docs/data/*_monthly_grid.csv and *_meta.json to GitHub.")


if __name__ == "__main__":
    convert_all_regions()
