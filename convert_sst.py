"""
convert_sst.py  —  LOCAL USE ONLY
Downloads NOAA ERSST v5 and produces docs/data/sst_grid.csv.

Source: NOAA Extended Reconstructed SST v5 (2°, monthly, 1854–present)
  Auto-downloaded (~70 MB) from NOAA PSL.

Output: docs/data/sst_grid.csv
  Columns: year, month, lat, lon, sst_anom, basin
  Resolution: 5° (aggregated from native 2°)
  Anomaly baseline: 1991–2020 monthly climatology

Usage:
  python convert_sst.py
"""

import csv
import json
import urllib.request
from pathlib import Path
from typing import Optional, List, Tuple
import numpy as np

ERSST_URL  = "https://downloads.psl.noaa.gov/Datasets/noaa.ersst.v5/sst.mnmean.nc"
ERSST_FILE = Path("sst.mnmean.nc")
DATA_DIR   = Path("docs/data")
CSV_OUT    = DATA_DIR / "sst_grid.csv"
META_OUT   = DATA_DIR / "sst_meta.json"

YEAR_START   = 1970
OUT_GRID     = 8.0          # 2° → 8° aggregation (keeps CSV ~20 MB)
CLIM_START   = 1991         # WMO standard climatology baseline
CLIM_END     = 2020

# Ocean basin bounding boxes — priority order, first match wins.
# lon in -180..180
BASINS: List[Tuple] = [
    ("Niño 3.4",        -5.0,   5.0, -170.0, -120.0),
    ("Tropical Pacific",-20.0,  20.0,  130.0,  -70.0),  # wraps antimeridian — handled below
    ("Tropical Atlantic",-20.0, 20.0,  -70.0,   20.0),
    ("Indian Ocean",    -45.0,  30.0,   20.0,  120.0),
    ("Southern Ocean",  -75.0, -45.0, -180.0,  180.0),
    ("North Pacific",    30.0,  65.0, -180.0, -100.0),
    ("North Atlantic",   30.0,  65.0,  -80.0,   30.0),
    ("Global",          -90.0,  90.0, -180.0,  180.0),  # catch-all
]


def assign_basin(lat: float, lon: float) -> Optional[str]:
    for name, lat_min, lat_max, lon_min, lon_max in BASINS:
        if not (lat_min <= lat < lat_max):
            continue
        # Handle Tropical Pacific which wraps the antimeridian (130E to 70W)
        if name == "Tropical Pacific":
            if lon >= 130.0 or lon <= -70.0:
                return name
        elif lon_min <= lon < lon_max:
            return name
    return None


def _reporthook(b: int, bs: int, total: int) -> None:
    pct = min(b * bs / total * 100, 100) if total > 0 else 0
    print(f"  {pct:5.1f}%", end="\r", flush=True)


def download_ersst() -> None:
    MIN_SIZE = 50 * 1024 * 1024  # 50 MB minimum — re-download if partial
    if ERSST_FILE.exists() and ERSST_FILE.stat().st_size >= MIN_SIZE:
        print(f"  {ERSST_FILE} already present ({ERSST_FILE.stat().st_size // (1024*1024)} MB)")
        return
    if ERSST_FILE.exists():
        ERSST_FILE.unlink()
    print(f"Downloading ERSST v5 (~70 MB) ...")
    urllib.request.urlretrieve(ERSST_URL, ERSST_FILE, _reporthook)
    print()


def convert_sst() -> dict:
    try:
        import netCDF4 as nc
        from netCDF4 import num2date
        from scipy.ndimage import gaussian_filter
    except ImportError as e:
        raise RuntimeError(f"pip install netCDF4 scipy  ({e})")

    download_ersst()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading {ERSST_FILE} ...")
    ds = nc.Dataset(ERSST_FILE)

    lat_raw = np.array(ds.variables["lat"][:])
    lon_raw = np.array(ds.variables["lon"][:])
    lon_180 = np.where(lon_raw > 180, lon_raw - 360, lon_raw)

    times = ds.variables["time"][:]
    dates = num2date(times, ds.variables["time"].units,
                     only_use_cftime_datetimes=False,
                     only_use_python_datetimes=True)

    # Filter to YEAR_START onward
    idx = [i for i, d in enumerate(dates) if d.year >= YEAR_START]
    years_arr  = np.array([dates[i].year  for i in idx])
    months_arr = np.array([dates[i].month for i in idx])
    T = len(idx)

    fill = float(getattr(ds.variables["sst"], "_FillValue", 1e30))
    t0, t1 = idx[0], idx[-1] + 1
    data = np.array(ds.variables["sst"][t0:t1], dtype=float)
    ds.close()

    # Mask land fill values
    data[np.abs(data) > 1e6] = np.nan
    print(f"  Loaded: {years_arr[0]}-{months_arr[0]:02d} → "
          f"{years_arr[-1]}-{months_arr[-1]:02d}  ({T} months)")

    # ── Compute 1991–2020 monthly climatology per cell ────────────────────────
    print(f"  Computing climatology ({CLIM_START}–{CLIM_END}) ...")
    clim_mask = (years_arr >= CLIM_START) & (years_arr <= CLIM_END)
    climatology = np.full((12, len(lat_raw), len(lon_raw)), np.nan)
    for m in range(1, 13):
        mask = clim_mask & (months_arr == m)
        with np.errstate(invalid="ignore"):
            climatology[m-1] = np.nanmean(data[mask], axis=0)

    # ── Compute anomaly ───────────────────────────────────────────────────────
    anom = np.full_like(data, np.nan)
    for t in range(T):
        m = months_arr[t] - 1
        anom[t] = data[t] - climatology[m]

    # ── Build 5° output grid ──────────────────────────────────────────────────
    out_lats = np.arange(-90.0,  90.0, OUT_GRID)
    out_lons = np.arange(-180.0, 180.0, OUT_GRID)
    cen_lat  = out_lats + OUT_GRID / 2
    cen_lon  = out_lons + OUT_GRID / 2
    n_lat, n_lon = len(out_lats), len(out_lons)

    lat_bins = np.floor((lat_raw - (-90.0)) / OUT_GRID).astype(int)
    lon_bins = np.floor((lon_180 - (-180.0)) / OUT_GRID).astype(int)
    lat_bins = np.clip(lat_bins, 0, n_lat - 1)
    lon_bins = np.clip(lon_bins, 0, n_lon - 1)

    # Aggregate 2° → 5°
    print("  Aggregating 2° → 5° ...")
    anom_coarse = np.full((T, n_lat, n_lon), np.nan)
    for bi in range(n_lat):
        li = lat_bins == bi
        if not li.any():
            continue
        for bj in range(n_lon):
            lj = lon_bins == bj
            if not lj.any():
                continue
            cell = anom[:, li, :][:, :, lj].reshape(T, -1)
            with np.errstate(invalid="ignore"):
                anom_coarse[:, bi, bj] = np.nanmean(cell, axis=1)

    # ── Assign basin to each 5° ocean cell ───────────────────────────────────
    cell_info = {}
    for bi, clat in enumerate(cen_lat):
        for bj, clon in enumerate(cen_lon):
            if np.all(np.isnan(anom_coarse[:, bi, bj])):
                continue   # land or no data
            basin = assign_basin(float(clat), float(clon))
            if basin is not None:
                cell_info[(bi, bj)] = (float(clat), float(clon), basin)

    print(f"  Ocean cells at {OUT_GRID}°: {len(cell_info)}")

    # ── ENSO classification ───────────────────────────────────────────────────
    try:
        from fetch_hurricanes import fetch_oni_classifications
        _, month_class = fetch_oni_classifications()
    except Exception:
        month_class = {}

    # ── Write CSV ─────────────────────────────────────────────────────────────
    print(f"  Writing {CSV_OUT} ...")
    with open(CSV_OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "month", "lat", "lon", "sst_anom", "enso", "basin"])
        for t in range(T):
            year  = int(years_arr[t])
            month = int(months_arr[t])
            enso  = month_class.get((year, month), "Neutral")
            for (bi, bj), (clat, clon, basin) in sorted(cell_info.items()):
                v = anom_coarse[t, bi, bj]
                if not np.isnan(v):
                    w.writerow([year, month,
                                round(clat, 2), round(clon, 2),
                                round(float(v), 2), enso, basin])

    first = f"{int(years_arr[0])}-{int(months_arr[0]):02d}"
    last  = f"{int(years_arr[-1])}-{int(months_arr[-1]):02d}"
    meta = {
        "first_month":  first,
        "last_month":   last,
        "n_months":     T,
        "n_cells":      len(cell_info),
        "grid_deg":     OUT_GRID,
        "source":       "NOAA ERSST v5 (2° monthly)",
        "variable":     "sst_anom (°C anomaly vs 1991-2020 climatology)",
        "basins":       sorted({v[2] for v in cell_info.values()}),
    }
    with open(META_OUT, "w") as f:
        json.dump(meta, f, indent=2)

    sz = CSV_OUT.stat().st_size // (1024 * 1024)
    print(f"  Done — {T} months, {len(cell_info)} cells  ({sz} MB)")
    return meta


if __name__ == "__main__":
    convert_sst()
