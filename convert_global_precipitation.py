"""
convert_global_precipitation.py  —  LOCAL USE ONLY
Downloads GPCC Full Data Monthly (2.5°) from NOAA PSL and writes per-region
CSV + JSON files used by the global precipitation page.

  python convert_global_precipitation.py

If auto-download fails, manually download:
  https://downloads.psl.noaa.gov/Datasets/gpcc/full_v7/precip.mon.total.2.5x2.5.nc
and place it as gpcc_precip_2.5.nc in this directory, then re-run.

Outputs docs/data/{region}_monthly_grid.csv and docs/data/{region}_meta.json
for each region defined in REGIONS below.  Commit those files to GitHub;
CI does not regenerate them (no NetCDF on CI).
"""

import csv
import json
import urllib.request
from pathlib import Path
from typing import Optional, List, Tuple
import numpy as np

GPCC_FILE  = Path("gpcc_precip_2.5.nc")
GPCC_URL   = ("https://downloads.psl.noaa.gov/Datasets/gpcc/full_v7/"
               "precip.mon.total.2.5x2.5.nc")
DATA_DIR   = Path("docs/data")
YEAR_START = 1970
GRID_DEG   = 2.5

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


def download_gpcc() -> None:
    print(f"Downloading GPCC 2.5° from NOAA PSL (~16 MB) ...")
    urllib.request.urlretrieve(GPCC_URL, GPCC_FILE,
        reporthook=lambda b, bs, tot: print(
            f"  {min(b*bs, tot)/1e6:.1f}/{tot/1e6:.1f} MB", end="\r", flush=True))
    print()


def convert_all_regions() -> None:
    try:
        import netCDF4 as nc
        from netCDF4 import num2date
    except ImportError:
        raise RuntimeError("pip install netCDF4")

    if not GPCC_FILE.exists():
        download_gpcc()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Opening GPCC NetCDF ...")
    ds = nc.Dataset(GPCC_FILE)

    # Detect precipitation variable name
    prcp_var = None
    for candidate in ("precip", "prcp", "precipitation", "pre", "p"):
        if candidate in ds.variables:
            prcp_var = candidate
            break
    if prcp_var is None:
        raise RuntimeError(
            f"Cannot find precip variable. Available: {list(ds.variables.keys())}")
    print(f"  Using variable '{prcp_var}'")

    # Lat / lon — GPCC from PSL uses 0–360 longitude convention
    lat_raw = np.array(ds.variables["lat"][:])
    lon_raw = np.array(ds.variables["lon"][:])
    lon     = np.where(lon_raw > 180, lon_raw - 360, lon_raw)

    times  = ds.variables["time"][:]
    dates  = num2date(times, ds.variables["time"].units,
                      only_use_cftime_datetimes=False,
                      only_use_python_datetimes=True)

    time_idx  = [i for i, d in enumerate(dates) if d.year >= YEAR_START]
    dates_sub = [dates[i] for i in time_idx]
    T         = len(time_idx)
    years_arr  = np.array([d.year  for d in dates_sub])
    months_arr = np.array([d.month for d in dates_sub])
    print(f"  {T} months from {YEAR_START} ({dates_sub[0].year}-{dates_sub[0].month:02d}"
          f" → {dates_sub[-1].year}-{dates_sub[-1].month:02d})")

    fill = float(getattr(ds.variables[prcp_var], "_FillValue", -9.96921e+36))

    # ENSO classification
    try:
        from fetch_hurricanes import fetch_oni_classifications
        _, month_class = fetch_oni_classifications()
    except Exception:
        month_class = {}

    for region_key, rcfg in REGIONS.items():
        print(f"\n── {rcfg['name']} ({'–'.join([str(YEAR_START), str(dates_sub[-1].year)])}) ──")

        lat_min, lat_max = rcfg["lat_min"], rcfg["lat_max"]
        lon_min, lon_max = rcfg["lon_min"], rcfg["lon_max"]

        lat_idx = np.where((lat_raw >= lat_min) & (lat_raw <= lat_max))[0]
        # Use original 0-360 lon indices but track converted lon values
        lon_mask = (lon >= lon_min) & (lon <= lon_max)
        lon_idx  = np.where(lon_mask)[0]

        sub_lat = lat_raw[lat_idx]
        sub_lon = lon[lon_idx]           # converted to -180/180

        print(f"  Grid: {len(lat_idx)} lat × {len(lon_idx)} lon")

        # Read just this region's slice across all time steps
        t0, t1 = time_idx[0], time_idx[-1] + 1
        raw = np.array(
            ds.variables[prcp_var][t0:t1, lat_idx[0]:lat_idx[-1]+1,
                                          lon_idx[0]:lon_idx[-1]+1],
            dtype=float,
        )
        raw[np.abs(raw - fill) < 1e30] = np.nan
        raw[raw < 0] = np.nan

        # Build output 2.5° cell centres (same as input, since GPCC is already 2.5°)
        # Assign subregion for each cell; keep only land cells (at least one non-NaN month)
        cell_info = {}   # (li, lj) → (centre_lat, centre_lon, subregion)
        for li, clat in enumerate(sub_lat):
            for lj, clon in enumerate(sub_lon):
                col = raw[:, li, lj]
                if np.all(np.isnan(col)):
                    continue   # ocean / no data
                sr = assign_subregion(float(clat), float(clon), rcfg["subregions"])
                if sr is not None:
                    cell_info[(li, lj)] = (float(clat), float(clon), sr)

        print(f"  Land cells with subregion: {len(cell_info)}")

        csv_path  = DATA_DIR / f"{region_key}_monthly_grid.csv"
        meta_path = DATA_DIR / f"{region_key}_meta.json"

        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["year", "month", "lat", "lon", "prcp_mm", "enso", "state"])
            for t in range(T):
                year  = int(years_arr[t])
                month = int(months_arr[t])
                enso  = month_class.get((year, month), "Neutral")
                for (li, lj), (clat, clon, sr) in sorted(cell_info.items()):
                    v = raw[t, li, lj]
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
            "grid_deg":    GRID_DEG,
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
