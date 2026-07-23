"""
convert_temperature.py  —  LOCAL USE ONLY
Single-source temperature pipeline for all regions (1970–present).

Source: GHCN-CAMS 2m air temperature (NOAA PSL)
  • One file covers the full globe, 1948–present, 0.5° monthly
  • Download (~500 MB):
      curl -O https://downloads.psl.noaa.gov/Datasets/ghcncams/air.mon.mean.nc

Usage:
  python convert_temperature.py             # all regions
  python convert_temperature.py india       # single region

Outputs (commit to GitHub — CI does not regenerate):
  docs/data/{region}_temp_monthly_grid.csv
  docs/data/{region}_temp_meta.json
"""

import csv
import json
import sys
from pathlib import Path
from typing import Optional, List, Tuple
import numpy as np

# ── Paths ──────────────────────────────────────────────────────────────────────
NC_FILE   = Path("air.mon.mean.nc")
DATA_DIR  = Path("docs/data")
YEAR_START = 1970
OUT_GRID   = 1.0    # aggregate 0.5° → 1.0° (keeps CSV ≤ 20 MB)
GAUSS_SIGMA = 1.0

# ── Region definitions (identical to precipitation) ────────────────────────────
REGIONS = {
    "usa": {
        "name": "United States",
        "lat_min": 24.0, "lat_max": 50.0,
        "lon_min": -125.0, "lon_max": -66.0,
        "subregions": [
            ("Northwest",    42.0, 50.0, -125.0, -110.0),
            ("Southwest",    31.0, 42.0, -125.0, -110.0),
            ("Northern Plains", 42.0, 50.0, -110.0,  -95.0),
            ("Southern Plains", 30.0, 42.0, -110.0,  -95.0),
            ("Midwest",      37.0, 50.0,  -95.0,  -80.0),
            ("Southeast",    24.0, 37.0,  -95.0,  -75.0),
            ("Northeast",    37.0, 50.0,  -80.0,  -66.0),
        ],
    },
    "india": {
        "name": "India",
        "lat_min": 5.0, "lat_max": 38.0,
        "lon_min": 67.0, "lon_max": 98.0,
        "subregions": [
            ("Northeast",   22.0, 38.0, 85.0, 98.0),
            ("North",       28.0, 38.0, 67.0, 85.0),
            ("West",        20.0, 28.0, 67.0, 77.0),
            ("Central",     17.0, 28.0, 77.0, 86.0),
            ("West Coast",   5.0, 20.0, 67.0, 77.0),
            ("South",        5.0, 17.0, 74.0, 86.0),
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
            ("Central",   -28.0, -22.0, 125.0, 140.0),
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
        "lon_min":  28.0, "lon_max": 52.0,
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


def load_ghcncams(year_start: int):
    """Load GHCN-CAMS air.mon.mean.nc, return (years, months, lat, lon_180, data_C)."""
    try:
        import netCDF4 as nc
        from netCDF4 import num2date
    except ImportError:
        raise RuntimeError("pip install netCDF4")

    if not NC_FILE.exists():
        raise FileNotFoundError(
            f"{NC_FILE} not found.\n"
            "Download with:\n"
            "  curl -O https://downloads.psl.noaa.gov/Datasets/ghcncams/air.mon.mean.nc"
        )

    print(f"Loading {NC_FILE}  (~500 MB, may take a moment) ...")
    ds = nc.Dataset(NC_FILE)

    # Variable name is 'air' in GHCN-CAMS
    temp_var = next((v for v in ("air", "tmp", "temp", "t2m") if v in ds.variables), None)
    if temp_var is None:
        raise RuntimeError(f"No temperature variable found. Available: {list(ds.variables.keys())}")

    lat_raw = np.array(ds.variables["lat"][:])
    lon_raw = np.array(ds.variables["lon"][:])
    lon_180 = np.where(lon_raw > 180, lon_raw - 360, lon_raw)

    times = ds.variables["time"][:]
    dates = num2date(times, ds.variables["time"].units,
                     only_use_cftime_datetimes=False,
                     only_use_python_datetimes=True)

    idx = [i for i, d in enumerate(dates) if d.year >= year_start]
    if not idx:
        ds.close()
        raise RuntimeError(f"No data found from {year_start} onwards")

    years_arr  = np.array([dates[i].year  for i in idx])
    months_arr = np.array([dates[i].month for i in idx])

    fill = float(getattr(ds.variables[temp_var], "_FillValue", -9.96921e+36))
    t0, t1 = idx[0], idx[-1] + 1
    data = np.array(ds.variables[temp_var][t0:t1], dtype=float)
    ds.close()

    data[np.abs(data - fill) < 1e25] = np.nan

    # Convert Kelvin → Celsius if needed (values > 200 K are in Kelvin)
    if np.nanmean(data[~np.isnan(data)][:1000]) > 200:
        print("  Converting Kelvin → Celsius ...")
        data -= 273.15

    print(f"  Loaded: {years_arr[0]}-{months_arr[0]:02d} → "
          f"{years_arr[-1]}-{months_arr[-1]:02d}  ({len(idx)} months)")
    return years_arr, months_arr, lat_raw, lon_180, data


def convert_all_regions(only: Optional[str] = None) -> None:
    try:
        from scipy.ndimage import gaussian_filter
    except ImportError:
        raise RuntimeError("pip install scipy")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    years_arr, months_arr, lat, lon_180, data_all = load_ghcncams(YEAR_START)
    T = len(years_arr)
    print(f"  {T} months total\n")

    # ENSO classification
    try:
        from fetch_hurricanes import fetch_oni_classifications
        _, month_class = fetch_oni_classifications()
    except Exception:
        month_class = {}

    for region_key, rcfg in REGIONS.items():
        if only and region_key != only:
            continue
        print(f"── {rcfg['name']} ──")

        lat_min, lat_max = rcfg["lat_min"], rcfg["lat_max"]
        lon_min, lon_max = rcfg["lon_min"], rcfg["lon_max"]

        lat_idx = np.where((lat >= lat_min) & (lat <= lat_max))[0]
        lon_idx = np.where((lon_180 >= lon_min) & (lon_180 <= lon_max))[0]

        if len(lat_idx) == 0 or len(lon_idx) == 0:
            print(f"  [WARN] No grid cells found for {rcfg['name']} — skipping")
            continue

        sub_lat = lat[lat_idx]
        sub_lon = lon_180[lon_idx]
        print(f"  Slice: {len(lat_idx)} lat × {len(lon_idx)} lon at 0.5°")

        raw = data_all[:, lat_idx[0]:lat_idx[-1]+1,
                           lon_idx[0]:lon_idx[-1]+1].copy()

        # NaN-aware Gaussian smoothing
        print(f"  Smoothing (σ={GAUSS_SIGMA}) ...")
        temp_smooth = np.full_like(raw, np.nan)
        for t in range(T):
            field    = raw[t]
            nan_mask = np.isnan(field)
            filled   = np.where(nan_mask, 0.0, field)
            weight   = (~nan_mask).astype(float)
            sm_num   = gaussian_filter(filled, sigma=GAUSS_SIGMA)
            sm_den   = gaussian_filter(weight, sigma=GAUSS_SIGMA)
            with np.errstate(invalid="ignore", divide="ignore"):
                temp_smooth[t] = np.where(sm_den > 0.1, sm_num / sm_den, np.nan)

        # Aggregate 0.5° → 1.0° (mean for temperature, not sum)
        out_lats = np.arange(lat_min, lat_max, OUT_GRID)
        out_lons = np.arange(lon_min, lon_max, OUT_GRID)
        cen_lat  = out_lats + OUT_GRID / 2
        cen_lon  = out_lons + OUT_GRID / 2
        n_lat, n_lon = len(out_lats), len(out_lons)

        lat_bins = np.floor((sub_lat - lat_min) / OUT_GRID).astype(int)
        lon_bins = np.floor((sub_lon - lon_min) / OUT_GRID).astype(int)

        temp_coarse = np.full((T, n_lat, n_lon), np.nan)
        for bi in range(n_lat):
            li_mask = lat_bins == bi
            if not li_mask.any():
                continue
            for bj in range(n_lon):
                lj_mask = lon_bins == bj
                if not lj_mask.any():
                    continue
                cell = temp_smooth[:, li_mask, :][:, :, lj_mask].reshape(T, -1)
                with np.errstate(invalid="ignore"):
                    temp_coarse[:, bi, bj] = np.nanmean(cell, axis=1)

        # Assign subregions
        cell_info = {}
        for bi, clat in enumerate(cen_lat):
            for bj, clon in enumerate(cen_lon):
                if np.all(np.isnan(temp_coarse[:, bi, bj])):
                    continue
                sr = assign_subregion(float(clat), float(clon), rcfg["subregions"])
                if sr is not None:
                    cell_info[(bi, bj)] = (float(clat), float(clon), sr)

        print(f"  Output cells at {OUT_GRID}°: {len(cell_info)}")

        csv_path  = DATA_DIR / f"{region_key}_temp_monthly_grid.csv"
        meta_path = DATA_DIR / f"{region_key}_temp_meta.json"

        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["year", "month", "lat", "lon", "temp_c", "enso", "state"])
            for t in range(T):
                year  = int(years_arr[t])
                month = int(months_arr[t])
                enso  = month_class.get((year, month), "Neutral")
                for (bi, bj), (clat, clon, sr) in sorted(cell_info.items()):
                    v = temp_coarse[t, bi, bj]
                    if not np.isnan(v):
                        w.writerow([year, month,
                                    round(clat, 2), round(clon, 2),
                                    round(float(v), 2), enso, sr])

        first = f"{int(years_arr[0])}-{int(months_arr[0]):02d}"
        last  = f"{int(years_arr[-1])}-{int(months_arr[-1]):02d}"
        meta = {
            "region_key":  region_key,
            "region_name": rcfg["name"],
            "first_month": first,
            "last_month":  last,
            "n_months":    T,
            "n_cells":     len(cell_info),
            "grid_deg":    OUT_GRID,
            "source":      "GHCN-CAMS 2m air temperature (NOAA PSL), 0.5° monthly",
            "variable":    "temp_c (degrees Celsius)",
            "smoothing":   f"gaussian_sigma{GAUSS_SIGMA}_then_mean_aggregated_to_{OUT_GRID}deg",
            "states":      sorted({v[2] for v in cell_info.values()}),
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        sz = csv_path.stat().st_size // (1024 * 1024)
        print(f"  → {csv_path.name} ({sz} MB)\n")

    print("Done. Commit docs/data/*_temp_monthly_grid.csv and *_temp_meta.json to GitHub.")


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only and only not in REGIONS:
        print(f"Unknown region '{only}'. Choose from: {', '.join(REGIONS)}")
        sys.exit(1)
    convert_all_regions(only)
