"""
convert_global_precipitation.py  —  LOCAL USE ONLY
Combines two sources to produce 1970–present global precipitation:
  • GPCC Full Data Monthly v7 (1901–2013, 0.5°) — already downloaded
  • CPC Unified Global Daily (1979–present, 0.5°) — auto-downloaded per year

Outputs docs/data/{region}_monthly_grid.csv + {region}_meta.json for each region.
Commit those files to GitHub; CI does not regenerate them.

Usage:
  python convert_global_precipitation.py

GPCC file needed (place in this directory):
  https://downloads.psl.noaa.gov/Datasets/gpcc/full_v7/precip.mon.total.v7.nc

CPC files (~60 MB/year, 2014–present) are auto-downloaded into cpc_cache/.
"""

import csv
import json
import urllib.request
from pathlib import Path
from typing import Optional, List, Tuple
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
GPCC_CANDIDATES = [
    Path("precip.mon.total.v7.nc"),
    Path("gpcc_precip_2.5.nc"),
    Path("gpcc_precip.nc"),
]
CPC_CACHE_DIR = Path("cpc_cache")
CPC_URL_TPL   = ("https://downloads.psl.noaa.gov/Datasets/cpc_global_precip/"
                  "precip.{year}.nc")
DATA_DIR      = Path("docs/data")

YEAR_START  = 1970
GAUSS_SIGMA = 1.0    # smoothing at native 0.5° resolution
OUT_GRID    = 1.0    # aggregate 0.5° → 1.0° to keep CSVs ≤ 20 MB

# ── Region definitions ────────────────────────────────────────────────────────
REGIONS = {
    "india": {
        "name": "India",
        "lat_min": 5.0, "lat_max": 38.0,
        "lon_min": 67.0, "lon_max": 98.0,
        "subregions": [
            ("Northeast",   22.0, 38.0, 85.0, 98.0),  # Assam, WB, NE states
            ("North",       28.0, 38.0, 67.0, 85.0),  # Punjab, UP, Bihar, Delhi
            ("West",        20.0, 28.0, 67.0, 77.0),  # Gujarat, Rajasthan
            ("Central",     17.0, 28.0, 77.0, 86.0),  # MP, Maharashtra, Odisha
            ("West Coast",   5.0, 20.0, 67.0, 77.0),  # Kerala, Goa, Karnataka coast
            ("South",        5.0, 17.0, 74.0, 86.0),  # Tamil Nadu, Andhra, Telangana
        ],
    },
    "australia": {
        "name": "Australia",
        "lat_min": -45.0, "lat_max": -9.0,
        "lon_min": 112.0, "lon_max": 155.0,
        "subregions": [
            ("Northern",  -22.0,  -9.0, 112.0, 155.0),  # NT + WA north + QLD north
            ("Queensland",-28.0, -15.0, 138.0, 155.0),  # Queensland east
            ("NSW-Vic",   -39.0, -28.0, 140.0, 155.0),  # NSW, Victoria, Tasmania
            ("Western",   -39.0, -22.0, 112.0, 125.0),  # WA south
            ("Central",   -28.0, -22.0, 125.0, 140.0),  # NT south + SA north (gap fix)
            ("South",     -39.0, -28.0, 125.0, 140.0),  # SA south
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
        "lon_min": 28.0,  "lon_max": 52.0,
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


def _reporthook(b: int, bs: int, total: int) -> None:
    pct = min(b * bs / total * 100, 100) if total > 0 else 0
    print(f"  {pct:5.1f}%", end="\r", flush=True)


# ── Source 1: GPCC Full Data Monthly v7 ──────────────────────────────────────
def load_gpcc(year_start: int, year_end: int):
    """
    Returns (years, months, lat, lon_180, data[T, nlat, nlon])
    where lon_180 is in -180..180 and data is in mm/month.
    """
    try:
        import netCDF4 as nc
        from netCDF4 import num2date
    except ImportError:
        raise RuntimeError("pip install netCDF4")

    gpcc_file = next((p for p in GPCC_CANDIDATES if p.exists()), None)
    if gpcc_file is None:
        raise FileNotFoundError(
            "GPCC file not found. Download:\n"
            "  https://downloads.psl.noaa.gov/Datasets/gpcc/full_v7/"
            "precip.mon.total.v7.nc\n"
            f"and save as {GPCC_CANDIDATES[0]}")

    print(f"  Loading GPCC from {gpcc_file} ...")
    ds  = nc.Dataset(gpcc_file)
    prcp_var = next((v for v in ("precip", "prcp", "pre", "p")
                     if v in ds.variables), None)
    if prcp_var is None:
        raise RuntimeError(f"No precip variable found in {gpcc_file}. "
                           f"Available: {list(ds.variables.keys())}")

    lat_raw = np.array(ds.variables["lat"][:])
    lon_raw = np.array(ds.variables["lon"][:])
    lon_180 = np.where(lon_raw > 180, lon_raw - 360, lon_raw)

    times  = ds.variables["time"][:]
    dates  = num2date(times, ds.variables["time"].units,
                      only_use_cftime_datetimes=False,
                      only_use_python_datetimes=True)

    idx = [i for i, d in enumerate(dates)
           if year_start <= d.year <= year_end]
    if not idx:
        ds.close()
        return None

    years_arr  = np.array([dates[i].year  for i in idx])
    months_arr = np.array([dates[i].month for i in idx])

    fill = float(getattr(ds.variables[prcp_var], "_FillValue", -9.96921e+36))
    t0, t1 = idx[0], idx[-1] + 1
    data = np.array(ds.variables[prcp_var][t0:t1], dtype=float)
    data[np.abs(data - fill) < 1e25] = np.nan
    data[data < 0] = np.nan
    ds.close()

    print(f"    GPCC: {years_arr[0]}-{months_arr[0]:02d} → "
          f"{years_arr[-1]}-{months_arr[-1]:02d}  ({len(idx)} months)")
    return years_arr, months_arr, lat_raw, lon_180, data


# ── Source 2: CPC Unified Global Daily Precipitation ─────────────────────────
def load_cpc_monthly(year_start: int, year_end: int, lat_ref, lon_ref_180):
    """
    Downloads per-year CPC files (if not cached), aggregates daily→monthly.
    Returns (years, months, data[T, nlat, nlon]) on the same lat/lon grid.
    """
    try:
        import netCDF4 as nc
        from netCDF4 import num2date
    except ImportError:
        raise RuntimeError("pip install netCDF4")

    CPC_CACHE_DIR.mkdir(exist_ok=True)

    import datetime
    current_year  = datetime.date.today().year
    current_month = datetime.date.today().month
    year_end = min(year_end, current_year)

    all_years, all_months, all_data = [], [], []

    for year in range(year_start, year_end + 1):
        cache_path = CPC_CACHE_DIR / f"precip.{year}.nc"
        MIN_SIZE = 10 * 1024 * 1024  # re-download if file is < 10 MB (partial)
        if not cache_path.exists() or cache_path.stat().st_size < MIN_SIZE:
            if cache_path.exists():
                cache_path.unlink()
            url = CPC_URL_TPL.format(year=year)
            print(f"  Downloading CPC {year} (~60 MB) ...")
            try:
                urllib.request.urlretrieve(url, cache_path, _reporthook)
                print()
            except Exception as e:
                print(f"\n  [WARN] Could not download {year}: {e}")
                if cache_path.exists():
                    cache_path.unlink()
                continue

        try:
            ds = nc.Dataset(cache_path)
        except Exception as e:
            print(f"  [WARN] Cannot open {cache_path}: {e}")
            continue

        prcp_var = next((v for v in ("precip", "prcp", "pre")
                         if v in ds.variables), None)
        if prcp_var is None:
            ds.close()
            continue

        lat_cpc = np.array(ds.variables["lat"][:])
        lon_raw = np.array(ds.variables["lon"][:])
        lon_cpc = np.where(lon_raw > 180, lon_raw - 360, lon_raw)

        # Verify grid matches GPCC
        if len(lat_cpc) != len(lat_ref) or not np.allclose(lat_cpc, lat_ref, atol=0.01):
            print(f"  [WARN] CPC {year} lat grid differs from GPCC — skipping")
            ds.close()
            continue

        times = ds.variables["time"][:]
        dates = num2date(times, ds.variables["time"].units,
                         only_use_cftime_datetimes=False,
                         only_use_python_datetimes=True)

        fill = float(getattr(ds.variables[prcp_var], "_FillValue", -9.96921e+36))
        raw  = np.array(ds.variables[prcp_var][:], dtype=float)
        ds.close()

        raw[np.abs(raw - fill) < 1e25] = np.nan
        raw[raw < 0] = np.nan

        # Aggregate daily → monthly totals (sum mm/day over all days = mm/month)
        months_in_year = sorted({d.month for d in dates})
        for m in months_in_year:
            if year == current_year and m > current_month:
                break
            day_mask = np.array([d.month == m for d in dates])
            if not day_mask.any():
                continue
            month_data = np.nansum(raw[day_mask], axis=0).astype(float)
            # Mark cells where ALL days were NaN as NaN
            all_nan = np.all(np.isnan(raw[day_mask]), axis=0)
            month_data[all_nan] = np.nan
            all_years.append(year)
            all_months.append(m)
            all_data.append(month_data)

        print(f"    CPC {year}: {len(months_in_year)} months aggregated")

    if not all_data:
        return None

    years_arr  = np.array(all_years)
    months_arr = np.array(all_months)
    data       = np.stack(all_data, axis=0)
    print(f"    CPC total: {years_arr[0]}-{months_arr[0]:02d} → "
          f"{years_arr[-1]}-{months_arr[-1]:02d}  ({len(years_arr)} months)")
    return years_arr, months_arr, data


# ── Main ──────────────────────────────────────────────────────────────────────
def convert_all_regions(only: Optional[str] = None) -> None:
    try:
        from scipy.ndimage import gaussian_filter
    except ImportError:
        raise RuntimeError("pip install scipy")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load GPCC (1970–2013) ─────────────────────────────────────────────
    print("=== Loading data sources ===")
    gpcc = load_gpcc(YEAR_START, 2013)
    if gpcc is None:
        raise RuntimeError("No GPCC data found in range")
    gpcc_years, gpcc_months, lat, lon_180, gpcc_data = gpcc

    # ── Load CPC (2014–present) ───────────────────────────────────────────
    print("\n  Fetching CPC Unified (2014–present) ...")
    cpc = load_cpc_monthly(2014, 2026, lat, lon_180)

    # ── Combine ───────────────────────────────────────────────────────────
    if cpc is not None:
        cpc_years, cpc_months, cpc_data = cpc
        years_arr  = np.concatenate([gpcc_years,  cpc_years])
        months_arr = np.concatenate([gpcc_months, cpc_months])
        data_all   = np.concatenate([gpcc_data,   cpc_data],  axis=0)
    else:
        print("  [WARN] No CPC data loaded — using GPCC only (1970–2013)")
        years_arr  = gpcc_years
        months_arr = gpcc_months
        data_all   = gpcc_data

    T = len(years_arr)
    print(f"\n=== Combined: {T} months "
          f"({years_arr[0]}-{months_arr[0]:02d} → "
          f"{years_arr[-1]}-{months_arr[-1]:02d}) ===\n")

    # ENSO classification per (year, month)
    try:
        from fetch_hurricanes import fetch_oni_classifications
        _, month_class = fetch_oni_classifications()
    except Exception:
        month_class = {}

    # ── Process each region ───────────────────────────────────────────────
    for region_key, rcfg in REGIONS.items():
        if only and region_key != only:
            continue
        print(f"── {rcfg['name']} ──")

        lat_min, lat_max = rcfg["lat_min"], rcfg["lat_max"]
        lon_min, lon_max = rcfg["lon_min"], rcfg["lon_max"]

        lat_idx  = np.where((lat >= lat_min) & (lat <= lat_max))[0]
        lon_mask = (lon_180 >= lon_min) & (lon_180 <= lon_max)
        lon_idx  = np.where(lon_mask)[0]

        sub_lat = lat[lat_idx]
        sub_lon = lon_180[lon_idx]
        print(f"  Slice: {len(lat_idx)} lat × {len(lon_idx)} lon at 0.5°")

        # Extract region slice
        raw = data_all[:, lat_idx[0]:lat_idx[-1]+1,
                            lon_idx[0]:lon_idx[-1]+1].copy()

        # NaN-aware Gaussian smoothing at native 0.5°
        print(f"  Smoothing (σ={GAUSS_SIGMA} cell = 0.5°) ...")
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

        # Aggregate 0.5° → 1.0° output grid
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
                cell  = prcp_smooth[:, li_mask, :][:, :, lj_mask].reshape(T, -1)
                valid = ~np.isnan(cell)
                cnt   = valid.sum(axis=1)
                sums  = np.where(valid, cell, 0.0).sum(axis=1)
                with np.errstate(invalid="ignore", divide="ignore"):
                    prcp_coarse[:, bi, bj] = np.where(cnt > 0, sums / cnt, np.nan)

        # Assign subregion to each 1.0° centre
        cell_info = {}
        for bi, clat in enumerate(cen_lat):
            for bj, clon in enumerate(cen_lon):
                if np.all(np.isnan(prcp_coarse[:, bi, bj])):
                    continue
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
            "sources":     "GPCC v7 (1970-2013) + CPC Unified (2014-present)",
            "smoothing":   f"gaussian_sigma{GAUSS_SIGMA}_then_aggregated_to_{OUT_GRID}deg",
            "states":      subregion_names,
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        sz = csv_path.stat().st_size // (1024 * 1024)
        print(f"  → {csv_path.name} ({sz} MB)\n")

    print("Done. Commit docs/data/*_monthly_grid.csv and *_meta.json to GitHub.")


if __name__ == "__main__":
    import sys
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only and only not in REGIONS:
        print(f"Unknown region '{only}'. Choose from: {', '.join(REGIONS)}")
        sys.exit(1)
    convert_all_regions(only=only)
