"""
fetch_hurricanes.py
Loads IBTrACS basin CSVs and ONI data, returns structured data for the
hurricane visualization page.
"""

import csv
import urllib.request
from collections import defaultdict
from pathlib import Path

IBTRACS_DIR = Path("jennie-IBTrACKS")

BASINS = ["NA", "EP", "WP", "NI", "SI", "SP"]

BASIN_NAMES = {
    "NA": "North Atlantic",
    "EP": "Eastern Pacific",
    "WP": "Western Pacific",
    "NI": "North Indian",
    "SI": "South Indian",
    "SP": "South Pacific",
}

BASIN_COLORS = {
    "NA": "#e74c3c",
    "EP": "#e67e22",
    "WP": "#3498db",
    "NI": "#9b59b6",
    "SI": "#1abc9c",
    "SP": "#f1c40f",
}

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

SUBSAMPLE  = 3
YEAR_START = 1970   # satellite era — global basin coverage reliable from here

# Maps each 3-month season code to its centre month (1=Jan … 12=Dec)
_SEASON_CENTRE = {
    "DJF": 1,  "JFM": 2,  "FMA": 3,  "MAM": 4,
    "AMJ": 5,  "MJJ": 6,  "JJA": 7,  "JAS": 8,
    "ASO": 9,  "SON": 10, "OND": 11, "NDJ": 12,
}


def fetch_oni_classifications() -> tuple:
    """
    Fetch ONI and classify using the official NOAA rule:
      5+ consecutive overlapping 3-month seasons with ONI >= +0.5 → El Niño episode
      5+ consecutive overlapping 3-month seasons with ONI <= -0.5 → La Niña episode
      Runs shorter than 5 seasons are Neutral regardless of anomaly magnitude.

    Returns:
      year_class  : {year: status}           — based on ASO season status
      month_class : {(year, centre_month): status} — episode status per season
    """
    print("Fetching ONI from NOAA/CPC ...")
    try:
        req = urllib.request.Request(ONI_URL, headers={"User-Agent": "ENSOTracker/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            content = r.read().decode("utf-8")
    except Exception as exc:
        print(f"  [WARN] Could not fetch ONI: {exc}")
        return {}, {}

    # Parse into chronological list
    rows = []
    for line in content.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0] not in _SEASON_CENTRE:
            continue
        try:
            year  = int(parts[1])
            anom  = float(parts[3])
        except ValueError:
            continue
        rows.append((year, _SEASON_CENTRE[parts[0]], anom))
    rows.sort(key=lambda x: (x[0], x[1]))

    # Raw per-season candidate labels
    candidates = []
    for _, _, anom in rows:
        if anom >= 0.5:
            candidates.append("El Niño")
        elif anom <= -0.5:
            candidates.append("La Niña")
        else:
            candidates.append("Neutral")

    # Apply 5-consecutive-season rule: only mark as episode if run >= 5
    status = ["Neutral"] * len(rows)
    for label in ("El Niño", "La Niña"):
        i = 0
        while i < len(candidates):
            if candidates[i] == label:
                j = i + 1
                while j < len(candidates) and candidates[j] == label:
                    j += 1
                if j - i >= 5:
                    for k in range(i, j):
                        status[k] = label
                i = j
            else:
                i += 1

    # Build month_class
    month_class: dict = {}
    for idx, (year, month, _) in enumerate(rows):
        month_class[(year, month)] = status[idx]

    # year_class: use ASO (centre month 9) for each year
    year_class: dict = {}
    for year, month, _ in rows:
        if month == 9:
            year_class[year] = month_class[(year, 9)]

    counts = {c: sum(1 for v in year_class.values() if v == c)
              for c in ("El Niño", "La Niña", "Neutral")}
    print(f"  NOAA-rule classified: {counts}")

    # Print episode periods
    _print_episodes(rows, status)

    return year_class, month_class


def _print_episodes(rows: list, status: list) -> None:
    """Print contiguous El Niño and La Niña episode spans."""
    season_names = {v: k for k, v in _SEASON_CENTRE.items()}
    episodes = {"El Niño": [], "La Niña": []}
    i = 0
    while i < len(rows):
        s = status[i]
        if s in episodes:
            j = i + 1
            while j < len(rows) and status[j] == s:
                j += 1
            yr_s, mo_s, _ = rows[i]
            yr_e, mo_e, _ = rows[j - 1]
            episodes[s].append(
                f"  {season_names[mo_s]} {yr_s} → {season_names[mo_e]} {yr_e} "
                f"({j - i} seasons)"
            )
            i = j
        else:
            i += 1
    for label, spans in episodes.items():
        print(f"\n{label} episodes ({len(spans)} total):")
        for span in spans:
            print(span)


def load_ibtracs() -> dict:
    """
    Load all 6 basin CSVs.
    Returns {(year, month): {basin: {tracknum: [(lat, lon, wind, angle), ...]}}}
    """
    print("Loading IBTrACS CSVs ...")
    data: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for basin in BASINS:
        path = IBTRACS_DIR / f"main1_{basin}.csv"
        if not path.exists():
            print(f"  [WARN] {path} not found — skipping")
            continue
        count = 0
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                time_str = row.get("time", "")
                if not time_str or len(time_str) < 7:
                    continue
                try:
                    year  = int(time_str[:4])
                    month = int(time_str[5:7])
                    lat   = float(row["lat"])
                    lon   = float(row["lon"])
                    wind  = float(row["wind"])         if row.get("wind")          else 0.0
                    angle = float(row["forward_angle"]) if row.get("forward_angle") else 0.0
                except (ValueError, KeyError):
                    continue
                tracknum = row.get("tracknum", "")
                data[(year, month)][basin][tracknum].append((lat, lon, wind, angle))
                count += 1
        print(f"  {basin}: {count:,} observations loaded")

    return data


def build_animation_data(ym_basin_tracks: dict, month_class: dict) -> dict:
    """
    Build per-(year, month) data for Plotly animation frames.
    ENSO label uses NOAA's official 5-consecutive-season episode definition
    looked up per (year, month) from month_class.
    Returns {"YYYY-MM": {basins, n_storms, enso, year, month}}
    """
    result = {}
    valid_keys = sorted(k for k in ym_basin_tracks if k[0] >= YEAR_START)

    for (year, month) in valid_keys:
        basins_data = ym_basin_tracks[(year, month)]
        basins_out  = {}
        total_storms = 0

        for basin in BASINS:
            tracks = basins_data.get(basin, {})
            lats, lons, winds, angles = [], [], [], []
            for obs_list in tracks.values():
                sampled = obs_list[::SUBSAMPLE]
                if obs_list and obs_list[-1] not in sampled:
                    sampled = sampled + [obs_list[-1]]
                for lat, lon, wind, ang in sampled:
                    lats.append(round(lat, 2))
                    lons.append(round(lon, 2))
                    winds.append(round(wind, 1))
                    angles.append(round(ang, 1))
                lats.append(None);  lons.append(None)
                winds.append(None); angles.append(None)
            basins_out[basin] = {"lats": lats, "lons": lons,
                                 "winds": winds, "angles": angles}
            total_storms += len(tracks)

        key = f"{year}-{month:02d}"
        result[key] = {
            "basins":   basins_out,
            "n_storms": total_storms,
            "enso":     month_class.get((year, month), "Neutral"),
            "year":     year,
            "month":    month,
        }
    return result


def compute_difference_grid(ym_basin_tracks: dict, month_class: dict,
                             grid_deg: float = 2.5) -> dict:
    """
    Bin all track observations into a lat/lon grid and compute
    El Niño minus non-El Niño wind-weighted track density.
    ENSO classification uses NOAA's official per-month episode status (month_class).
    Normalises by number of unique El Niño / other months.
    """
    lat_bins = int(180 / grid_deg)
    lon_bins = int(360 / grid_deg)

    en_grid:   dict = defaultdict(float)
    oth_grid:  dict = defaultdict(float)
    en_months:  int = 0
    oth_months: int = 0

    for (year, month), basins in ym_basin_tracks.items():
        if year < YEAR_START:
            continue
        is_el_nino = (month_class.get((year, month), "Neutral") == "El Niño")
        grid = en_grid if is_el_nino else oth_grid
        if is_el_nino:
            en_months += 1
        else:
            oth_months += 1

        for basin_tracks in basins.values():
            for obs_list in basin_tracks.values():
                for lat, lon, wind, *_ in obs_list:
                    i = max(0, min(lat_bins - 1, int((lat + 90)  / grid_deg)))
                    j = max(0, min(lon_bins - 1, int((lon + 180) / grid_deg)))
                    grid[(i, j)] += wind

    if en_months  > 0: en_grid  = {k: v / en_months  for k, v in en_grid.items()}
    if oth_months > 0: oth_grid = {k: v / oth_months for k, v in oth_grid.items()}

    all_cells = set(en_grid) | set(oth_grid)
    points = []
    for (i, j) in all_cells:
        diff = en_grid.get((i, j), 0.0) - oth_grid.get((i, j), 0.0)
        if abs(diff) < 0.5:
            continue
        lat_c = round(-90  + (i + 0.5) * grid_deg, 2)
        lon_c = round(-180 + (j + 0.5) * grid_deg, 2)
        points.append({"lat": lat_c, "lon": lon_c, "diff": round(diff, 4)})

    print(f"  Difference grid: {len(points)} non-trivial cells "
          f"({en_months} El Niño months vs {oth_months} other months)")
    return {"points": points, "n_el_nino": en_months, "n_other": oth_months, "grid_deg": grid_deg}


def compute_basin_footprints(ym_basin_tracks: dict, grid_deg: float = 2.5) -> dict:
    """
    Unique 2.5° grid cells ever visited by each basin's storms (post-YEAR_START).
    Ocean-only by construction — used as static background shading.
    """
    cells: dict = {b: set() for b in BASINS}
    for (year, month), basins in ym_basin_tracks.items():
        if year < YEAR_START:
            continue
        for basin, tracks in basins.items():
            for obs_list in tracks.values():
                for lat, lon, *_ in obs_list[::3]:
                    rlat = round(round(lat / grid_deg) * grid_deg, 1)
                    rlon = round(round(lon / grid_deg) * grid_deg, 1)
                    cells[basin].add((rlat, rlon))
    return {
        b: {"lats": [c[0] for c in pts], "lons": [c[1] for c in pts]}
        for b, pts in cells.items()
    }


def fetch_hurricane_data() -> dict:
    year_class, month_class = fetch_oni_classifications()
    ym_basin_tracks  = load_ibtracs()
    animation        = build_animation_data(ym_basin_tracks, month_class)
    diff_map         = compute_difference_grid(ym_basin_tracks, month_class)
    basin_footprints = compute_basin_footprints(ym_basin_tracks)
    return {
        "animation":        animation,
        "diff_map":         diff_map,
        "basin_footprints": basin_footprints,
        "year_class":       year_class,
        "basin_colors":     BASIN_COLORS,
        "basin_names":      BASIN_NAMES,
    }


if __name__ == "__main__":
    data = fetch_hurricane_data()
    keys = sorted(data["animation"].keys())
    print(f"\nFrames: {keys[0]} → {keys[-1]}  ({len(keys)} total)")
    print(f"Diff map points: {len(data['diff_map']['points'])}")
