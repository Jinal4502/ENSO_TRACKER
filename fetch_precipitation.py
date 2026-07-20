"""
fetch_precipitation.py
Reads docs/data/sw_meta.json (written by convert_precipitation.py) and
returns the metadata dict that update_enso.py passes to render_precipitation.

No NetCDF or heavy dependencies — runs fine in GitHub Actions CI.
To regenerate the CSVs from a new NClimGrid file, run convert_precipitation.py locally.
"""

import json
from pathlib import Path

META_FILE = Path("docs/data/sw_meta.json")


def fetch_precipitation_data() -> dict:
    if not META_FILE.exists():
        print(f"  [WARN] {META_FILE} not found — run convert_precipitation.py locally first")
        return {}
    with open(META_FILE) as f:
        meta = json.load(f)
    states = ", ".join(meta.get("states", []))
    print(f"  SW precipitation: {meta['first_month']} → {meta['last_month']}, "
          f"{meta['n_cells']} cells at {meta['grid_deg']}°  [{states}]")
    return meta


if __name__ == "__main__":
    print(fetch_precipitation_data())
