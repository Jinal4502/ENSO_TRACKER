# """
# convert_sst.py — LOCAL USE ONLY
# Downloads NOAA ERSST v5 and produces docs/data/sst_grid.csv.

# Source: NOAA Extended Reconstructed SST v5 (2°, monthly, 1854–present)
# Output columns: year, month, lat, lon, sst_anom, sst_raw, enso, basin
# Anomaly baseline: 1991–2020 monthly climatology
# """

# import csv
# import json
# import urllib.request
# from pathlib import Path
# from typing import List, Optional, Tuple

# import numpy as np

# ERSST_URL = "https://downloads.psl.noaa.gov/Datasets/noaa.ersst.v5/sst.mnmean.nc"
# ERSST_FILE = Path("sst.mnmean.nc")
# DATA_DIR = Path("docs/data")
# CSV_OUT = DATA_DIR / "sst_grid.csv"
# META_OUT = DATA_DIR / "sst_meta.json"

# YEAR_START = 1970
# OUT_GRID = 8.0
# CLIM_START = 1991
# CLIM_END = 2020

# BASINS: List[Tuple[str, float, float, float, float]] = [
#     # ENSO monitoring region (subset of Tropical Pacific)
#     ("Niño 3.4",          -5.0,   5.0,  -170.0, -120.0),
#     # Tropical belt — lon_min > lon_max means wraps across antimeridian
#     ("Tropical Pacific",  -20.0,  20.0,   120.0,  -70.0),
#     ("Tropical Atlantic", -20.0,  20.0,   -70.0,   20.0),
#     ("Indian Ocean",      -45.0,  45.0,    20.0,  120.0),  # extended north to 45°N
#     # Extratropical southern hemisphere
#     ("South Pacific",     -45.0, -20.0,   120.0,  -70.0),  # same lon-wrap as Tropical Pacific
#     ("South Atlantic",    -45.0, -20.0,   -70.0,   20.0),
#     # High southern latitudes (extended from -75 to -90)
#     ("Southern Ocean",    -90.0, -45.0,  -180.0,  180.0),
#     # Northern hemisphere — North Pacific uses wider lon range to cover western Pacific
#     ("North Pacific",      20.0,  65.0,   120.0, -100.0),  # wraps: lon ≥ 120 or lon < -100
#     ("North Atlantic",     20.0,  65.0,  -100.0,   45.0),  # wider: includes Gulf, Med
#     # Arctic
#     ("Arctic Ocean",       65.0,  90.0,  -180.0,  180.0),
# ]


# def assign_basin(lat: float, lon: float) -> Optional[str]:
#     for name, lat_min, lat_max, lon_min, lon_max in BASINS:
#         if not (lat_min <= lat < lat_max):
#             continue
#         if lon_min > lon_max:  # wraps around antimeridian (Pacific basins)
#             if lon >= lon_min or lon < lon_max:
#                 return name
#         elif lon_min <= lon < lon_max:
#             return name
#     return None


# def _reporthook(blocks: int, block_size: int, total: int) -> None:
#     pct = min(blocks * block_size / total * 100, 100) if total > 0 else 0
#     print(f"  {pct:5.1f}%", end="\r", flush=True)


# def download_ersst() -> None:
#     min_size = 50 * 1024 * 1024
#     if ERSST_FILE.exists() and ERSST_FILE.stat().st_size >= min_size:
#         size_mb = ERSST_FILE.stat().st_size // (1024 * 1024)
#         print(f"  {ERSST_FILE} already present ({size_mb} MB)")
#         return
#     if ERSST_FILE.exists():
#         ERSST_FILE.unlink()
#     print("Downloading ERSST v5 (~70 MB) ...")
#     urllib.request.urlretrieve(ERSST_URL, ERSST_FILE, _reporthook)
#     print()


# def _grid_edges(start: float, stop: float, step: float) -> np.ndarray:
#     """Return edges covering [start, stop] without creating a center at ±90°."""
#     edges = np.arange(start, stop, step, dtype=float)
#     if edges.size == 0 or not np.isclose(edges[0], start):
#         edges = np.insert(edges, 0, start)
#     if not np.isclose(edges[-1], stop):
#         edges = np.append(edges, stop)
#     return edges


# def convert_sst() -> dict:
#     try:
#         import netCDF4 as nc
#         from netCDF4 import num2date
#     except ImportError as exc:
#         raise RuntimeError(f"pip install netCDF4 ({exc})") from exc

#     download_ersst()
#     DATA_DIR.mkdir(parents=True, exist_ok=True)

#     print(f"Loading {ERSST_FILE} ...")
#     with nc.Dataset(ERSST_FILE) as ds:
#         lat_raw = np.asarray(ds.variables["lat"][:], dtype=float)
#         lon_raw = np.asarray(ds.variables["lon"][:], dtype=float)
#         lon_180 = ((lon_raw + 180.0) % 360.0) - 180.0

#         times = ds.variables["time"][:]
#         dates = num2date(
#             times,
#             ds.variables["time"].units,
#             only_use_cftime_datetimes=False,
#             only_use_python_datetimes=True,
#         )
#         idx = [i for i, d in enumerate(dates) if d.year >= YEAR_START]
#         if not idx:
#             raise RuntimeError(f"No ERSST records found from {YEAR_START} onward")

#         years_arr = np.array([dates[i].year for i in idx], dtype=np.int16)
#         months_arr = np.array([dates[i].month for i in idx], dtype=np.uint8)
#         data = np.asarray(ds.variables["sst"][idx[0] : idx[-1] + 1], dtype=float)

#     data[np.abs(data) > 1e6] = np.nan
#     t_count = len(idx)
#     print(
#         f"  Loaded: {years_arr[0]}-{months_arr[0]:02d} → "
#         f"{years_arr[-1]}-{months_arr[-1]:02d} ({t_count} months)"
#     )

#     print(f"  Computing climatology ({CLIM_START}–{CLIM_END}) ...")
#     clim_mask = (years_arr >= CLIM_START) & (years_arr <= CLIM_END)
#     climatology = np.full((12, len(lat_raw), len(lon_raw)), np.nan)
#     for month in range(1, 13):
#         mask = clim_mask & (months_arr == month)
#         with np.errstate(invalid="ignore"):
#             climatology[month - 1] = np.nanmean(data[mask], axis=0)

#     anom = np.empty_like(data)
#     for t in range(t_count):
#         anom[t] = data[t] - climatology[months_arr[t] - 1]

#     # Use explicit edges and midpoint centers. Because 8 does not divide 180,
#     # the final latitude band is 86–90° and its center is 88°, not 90°.
#     lat_edges = _grid_edges(-90.0, 90.0, OUT_GRID)
#     lon_edges = _grid_edges(-180.0, 180.0, OUT_GRID)
#     cen_lat = (lat_edges[:-1] + lat_edges[1:]) / 2.0
#     cen_lon = (lon_edges[:-1] + lon_edges[1:]) / 2.0
#     n_lat, n_lon = len(cen_lat), len(cen_lon)

#     lat_bins = np.searchsorted(lat_edges, lat_raw, side="right") - 1
#     lon_bins = np.searchsorted(lon_edges, lon_180, side="right") - 1
#     lat_bins = np.clip(lat_bins, 0, n_lat - 1)
#     lon_bins = np.clip(lon_bins, 0, n_lon - 1)

#     print(f"  Aggregating 2° → nominal {OUT_GRID:g}° ...")
#     anom_coarse = np.full((t_count, n_lat, n_lon), np.nan)
#     raw_coarse = np.full((t_count, n_lat, n_lon), np.nan)

#     for bi in range(n_lat):
#         lat_mask = lat_bins == bi
#         if not lat_mask.any():
#             continue
#         for bj in range(n_lon):
#             lon_mask = lon_bins == bj
#             if not lon_mask.any():
#                 continue
#             cell_anom = anom[:, lat_mask, :][:, :, lon_mask].reshape(t_count, -1)
#             cell_raw = data[:, lat_mask, :][:, :, lon_mask].reshape(t_count, -1)
#             with np.errstate(invalid="ignore"):
#                 anom_coarse[:, bi, bj] = np.nanmean(cell_anom, axis=1)
#                 raw_coarse[:, bi, bj] = np.nanmean(cell_raw, axis=1)

#     cell_info = {}
#     for bi, clat in enumerate(cen_lat):
#         for bj, clon in enumerate(cen_lon):
#             if np.all(np.isnan(raw_coarse[:, bi, bj])):
#                 continue
#             basin = assign_basin(float(clat), float(clon))
#             if basin is not None:
#                 cell_info[(bi, bj)] = (float(clat), float(clon), basin)

#     print(f"  Ocean cells: {len(cell_info)}")

#     try:
#         from fetch_hurricanes import fetch_oni_classifications

#         _, month_class = fetch_oni_classifications()
#     except Exception as exc:
#         print(f"  ONI classification unavailable; using Neutral ({exc})")
#         month_class = {}

#     print(f"  Writing {CSV_OUT} ...")
#     with CSV_OUT.open("w", newline="", encoding="utf-8") as file_obj:
#         writer = csv.writer(file_obj)
#         writer.writerow(
#             ["year", "month", "lat", "lon", "sst_anom", "sst_raw", "enso", "basin"]
#         )
#         ordered_cells = sorted(cell_info.items())
#         for t in range(t_count):
#             year = int(years_arr[t])
#             month = int(months_arr[t])
#             enso = month_class.get((year, month), "Neutral")
#             for (bi, bj), (clat, clon, basin) in ordered_cells:
#                 anomaly = anom_coarse[t, bi, bj]
#                 raw = raw_coarse[t, bi, bj]
#                 if np.isnan(anomaly) or np.isnan(raw):
#                     continue
#                 writer.writerow(
#                     [
#                         year,
#                         month,
#                         round(clat, 3),
#                         round(clon, 3),
#                         round(float(anomaly), 2),
#                         round(float(raw), 2),
#                         enso,
#                         basin,
#                     ]
#                 )

#     first = f"{int(years_arr[0])}-{int(months_arr[0]):02d}"
#     last = f"{int(years_arr[-1])}-{int(months_arr[-1]):02d}"
#     meta = {
#         "first_month": first,
#         "last_month": last,
#         "n_months": t_count,
#         "n_cells": len(cell_info),
#         "grid_deg": OUT_GRID,
#         "lat_edges": [float(x) for x in lat_edges],
#         "lon_edges": [float(x) for x in lon_edges],
#         "source": "NOAA ERSST v5 (2° monthly)",
#         "variable": "sst_anom and sst_raw (°C); anomaly vs 1991–2020 climatology",
#         "basins": sorted({value[2] for value in cell_info.values()}),
#     }
#     with META_OUT.open("w", encoding="utf-8") as file_obj:
#         json.dump(meta, file_obj, indent=2)

#     size_mb = CSV_OUT.stat().st_size // (1024 * 1024)
#     print(f"  Done — {t_count} months, {len(cell_info)} cells ({size_mb} MB)")
#     return meta


# if __name__ == "__main__":
#     convert_sst()

"""
convert_sst.py — LOCAL USE ONLY
Downloads NOAA ERSST v5 and produces docs/data/sst_grid.csv.

Source: NOAA Extended Reconstructed SST v5 (2°, monthly, 1854–present)
Output columns: year, month, lat, lon, sst_anom, sst_raw, enso, basin, is_nino34
Anomaly baseline: 1991–2020 monthly climatology
"""

import csv
import json
import urllib.request
from pathlib import Path

import numpy as np

ERSST_URL = "https://downloads.psl.noaa.gov/Datasets/noaa.ersst.v5/sst.mnmean.nc"
ERSST_FILE = Path("sst.mnmean.nc")
DATA_DIR = Path("docs/data")
CSV_OUT = DATA_DIR / "sst_grid.csv"
META_OUT = DATA_DIR / "sst_meta.json"

YEAR_START = 1970
OUT_GRID = 8.0
CLIM_START = 1991
CLIM_END = 2020

BASIN_ORDER = [
    "North Pacific",
    "South Pacific",
    "North Atlantic",
    "South Atlantic",
    "Indian Ocean",
    "Southern Ocean",
    "Arctic Ocean",
]


def normalize_lon(lon: float) -> float:
    """Normalize longitude to the interval [-180, 180)."""
    return ((lon + 180.0) % 360.0) - 180.0


def assign_basin(lat: float, lon: float) -> str:
    """Assign every valid ocean cell to exactly one broad ocean basin.

    This is a complete, mutually exclusive geographic partition intended for
    coarse global SST aggregation. Land has already been removed by the ERSST
    missing-value mask before this function is called.
    """
    lon = normalize_lon(lon)

    if lat < -45.0:
        return "Southern Ocean"
    if lat >= 66.0:
        return "Arctic Ocean"

    # Indian sector: east of Africa through Indonesia/Australia.
    if 20.0 <= lon < 147.0:
        return "Indian Ocean"

    # Atlantic sector; split at the equator.
    if -70.0 <= lon < 20.0:
        return "North Atlantic" if lat >= 0.0 else "South Atlantic"

    # All remaining non-polar ocean cells are Pacific.
    return "North Pacific" if lat >= 0.0 else "South Pacific"


def is_nino34_cell(lat: float, lon: float) -> bool:
    """Return True when the grid-cell center lies in the Niño 3.4 box."""
    lon = normalize_lon(lon)
    return -5.0 <= lat <= 5.0 and -170.0 <= lon <= -120.0


def _reporthook(blocks: int, block_size: int, total: int) -> None:
    pct = min(blocks * block_size / total * 100, 100) if total > 0 else 0
    print(f"  {pct:5.1f}%", end="\r", flush=True)


def download_ersst() -> None:
    min_size = 50 * 1024 * 1024
    if ERSST_FILE.exists() and ERSST_FILE.stat().st_size >= min_size:
        size_mb = ERSST_FILE.stat().st_size // (1024 * 1024)
        print(f"  {ERSST_FILE} already present ({size_mb} MB)")
        return
    if ERSST_FILE.exists():
        ERSST_FILE.unlink()
    print("Downloading ERSST v5 (~70 MB) ...")
    urllib.request.urlretrieve(ERSST_URL, ERSST_FILE, _reporthook)
    print()


def convert_sst() -> dict:
    try:
        import netCDF4 as nc
        from netCDF4 import num2date
    except ImportError as exc:
        raise RuntimeError(f"pip install netCDF4 ({exc})") from exc

    download_ersst()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading {ERSST_FILE} ...")
    with nc.Dataset(ERSST_FILE) as ds:
        lat_raw = np.asarray(ds.variables["lat"][:], dtype=float)
        lon_raw = np.asarray(ds.variables["lon"][:], dtype=float)
        lon_180 = ((lon_raw + 180.0) % 360.0) - 180.0

        times = ds.variables["time"][:]
        dates = num2date(
            times,
            ds.variables["time"].units,
            only_use_cftime_datetimes=False,
            only_use_python_datetimes=True,
        )
        idx = [i for i, d in enumerate(dates) if d.year >= YEAR_START]
        if not idx:
            raise RuntimeError(f"No ERSST records found from {YEAR_START} onward")

        years_arr = np.array([dates[i].year for i in idx], dtype=np.int16)
        months_arr = np.array([dates[i].month for i in idx], dtype=np.uint8)
        data = np.asarray(ds.variables["sst"][idx[0] : idx[-1] + 1], dtype=float)

    data[np.abs(data) > 1e6] = np.nan
    t_count = len(idx)
    print(
        f"  Loaded: {years_arr[0]}-{months_arr[0]:02d} → "
        f"{years_arr[-1]}-{months_arr[-1]:02d} ({t_count} months)"
    )

    print(f"  Computing climatology ({CLIM_START}–{CLIM_END}) ...")
    clim_mask = (years_arr >= CLIM_START) & (years_arr <= CLIM_END)
    climatology = np.full((12, len(lat_raw), len(lon_raw)), np.nan)
    for month in range(1, 13):
        mask = clim_mask & (months_arr == month)
        with np.errstate(invalid="ignore"):
            climatology[month - 1] = np.nanmean(data[mask], axis=0)

    anom = np.empty_like(data)
    for t in range(t_count):
        anom[t] = data[t] - climatology[months_arr[t] - 1]

    # Original aggregation approach: fixed 8° bins anchored at -90°/-180°.
    # This intentionally preserves the original CSV layout. The final northern
    # latitude bin is partial (86° to 90°) and is represented by center 90°.
    # The renderer must use clockwise GeoJSON polygon winding.
    out_lats = np.arange(-90.0, 90.0, OUT_GRID)
    out_lons = np.arange(-180.0, 180.0, OUT_GRID)
    cen_lat = out_lats + OUT_GRID / 2.0
    cen_lon = out_lons + OUT_GRID / 2.0
    n_lat, n_lon = len(out_lats), len(out_lons)

    lat_bins = np.floor((lat_raw + 90.0) / OUT_GRID).astype(int)
    lon_bins = np.floor((lon_180 + 180.0) / OUT_GRID).astype(int)
    lat_bins = np.clip(lat_bins, 0, n_lat - 1)
    lon_bins = np.clip(lon_bins, 0, n_lon - 1)

    print(f"  Aggregating 2° → {OUT_GRID:g}° ...")
    anom_coarse = np.full((t_count, n_lat, n_lon), np.nan)
    raw_coarse = np.full((t_count, n_lat, n_lon), np.nan)

    for bi in range(n_lat):
        lat_mask = lat_bins == bi
        if not lat_mask.any():
            continue
        for bj in range(n_lon):
            lon_mask = lon_bins == bj
            if not lon_mask.any():
                continue
            cell_anom = anom[:, lat_mask, :][:, :, lon_mask].reshape(t_count, -1)
            cell_raw = data[:, lat_mask, :][:, :, lon_mask].reshape(t_count, -1)
            with np.errstate(invalid="ignore"):
                anom_coarse[:, bi, bj] = np.nanmean(cell_anom, axis=1)
                raw_coarse[:, bi, bj] = np.nanmean(cell_raw, axis=1)

    cell_info = {}
    for bi, clat in enumerate(cen_lat):
        for bj, clon in enumerate(cen_lon):
            if np.all(np.isnan(raw_coarse[:, bi, bj])):
                continue
            lat = float(clat)
            lon = float(clon)
            basin = assign_basin(lat, lon)
            cell_info[(bi, bj)] = (lat, lon, basin, is_nino34_cell(lat, lon))

    print(f"  Ocean cells: {len(cell_info)}")

    try:
        from fetch_hurricanes import fetch_oni_classifications

        _, month_class = fetch_oni_classifications()
    except Exception as exc:
        print(f"  ONI classification unavailable; using Neutral ({exc})")
        month_class = {}

    print(f"  Writing {CSV_OUT} ...")
    with CSV_OUT.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(
            [
                "year", "month", "lat", "lon", "sst_anom", "sst_raw",
                "enso", "basin", "is_nino34"
            ]
        )
        ordered_cells = sorted(cell_info.items())
        for t in range(t_count):
            year = int(years_arr[t])
            month = int(months_arr[t])
            enso = month_class.get((year, month), "Neutral")
            for (bi, bj), (clat, clon, basin, is_nino34) in ordered_cells:
                anomaly = anom_coarse[t, bi, bj]
                raw = raw_coarse[t, bi, bj]
                if np.isnan(anomaly) or np.isnan(raw):
                    continue
                writer.writerow(
                    [
                        year,
                        month,
                        round(clat, 3),
                        round(clon, 3),
                        round(float(anomaly), 2),
                        round(float(raw), 2),
                        enso,
                        basin,
                        int(is_nino34),
                    ]
                )

    first = f"{int(years_arr[0])}-{int(months_arr[0]):02d}"
    last = f"{int(years_arr[-1])}-{int(months_arr[-1]):02d}"
    meta = {
        "first_month": first,
        "last_month": last,
        "n_months": t_count,
        "n_cells": len(cell_info),
        "grid_deg": OUT_GRID,
        "source": "NOAA ERSST v5 (2° monthly)",
        "variable": "sst_anom and sst_raw (°C); anomaly vs 1991–2020 climatology",
        "basins": BASIN_ORDER,
        "analysis_regions": ["Niño 3.4"],
    }
    with META_OUT.open("w", encoding="utf-8") as file_obj:
        json.dump(meta, file_obj, indent=2)

    size_mb = CSV_OUT.stat().st_size // (1024 * 1024)
    print(f"  Done — {t_count} months, {len(cell_info)} cells ({size_mb} MB)")
    return meta


if __name__ == "__main__":
    convert_sst()