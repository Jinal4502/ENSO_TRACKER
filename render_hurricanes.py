"""
render_hurricanes.py
Generates docs/hurricanes.html — animated global TC track slider + difference map.
"""

import json
from fetch_hurricanes import BASINS, BASIN_NAMES, BASIN_COLORS

ENSO_COLORS = {"El Niño": "#ff6b35", "La Niña": "#4a9eff", "Neutral": "#8b949e"}

# Saffir-Simpson category colors mapped to 0–185 kt range
WIND_COLORSCALE = [
    [0.000, "#5ebaff"],   # TD  (0 kt)
    [0.184, "#5ebaff"],
    [0.184, "#00faf4"],   # TS  (34 kt)
    [0.346, "#00faf4"],
    [0.346, "#ffffcc"],   # Cat 1 (64 kt)
    [0.449, "#ffffcc"],
    [0.449, "#ffe775"],   # Cat 2 (83 kt)
    [0.519, "#ffe775"],
    [0.519, "#ffc140"],   # Cat 3 (96 kt)
    [0.611, "#ffc140"],
    [0.611, "#ff8f20"],   # Cat 4 (113 kt)
    [0.741, "#ff8f20"],
    [0.741, "#ff6060"],   # Cat 5 (137 kt)
    [1.000, "#cc0000"],
]

N_BASINS = len(BASINS)   # 6 storm traces at indices 0-5


def _marker_cfg(winds: list, angles: list) -> dict:
    return {
        "symbol":     "arrow",
        "angle":      angles,
        "color":      winds,
        "colorscale": WIND_COLORSCALE,
        "cmin": 0, "cmax": 185,
        "size": 7,
        "opacity": 0.85,
    }


_MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
                "Jul","Aug","Sep","Oct","Nov","Dec"]

def _annotations(year: int, month: int, enso: str, n_storms: int) -> list:
    return [
        {"x": 0.01, "y": 0.99, "xref": "paper", "yref": "paper",
         "text": f"<b>{_MONTH_NAMES[month-1]} {year}</b>", "showarrow": False,
         "xanchor": "left", "yanchor": "top",
         "font": {"size": 24, "color": "#c9d1d9"}},
        {"x": 0.01, "y": 0.91, "xref": "paper", "yref": "paper",
         "text": f"<b>{enso}</b>", "showarrow": False,
         "xanchor": "left", "yanchor": "top",
         "font": {"size": 16, "color": ENSO_COLORS[enso]}},
        {"x": 0.01, "y": 0.85, "xref": "paper", "yref": "paper",
         "text": f"{n_storms} active tracks", "showarrow": False,
         "xanchor": "left", "yanchor": "top",
         "font": {"size": 13, "color": "#8b949e"}},
    ]


def render_hurricanes(data: dict, output: str = "docs/hurricanes.html") -> None:
    animation        = data["animation"]
    diff_map         = data["diff_map"]
    basin_footprints = data["basin_footprints"]

    sorted_keys = sorted(animation.keys())   # "YYYY-MM" strings sort correctly
    first_key   = sorted_keys[0]
    first_data  = animation[first_key]

    # ── Traces 0-5: static basin footprint shading (ocean-only) ──────────
    footprint_traces = []
    for basin in BASINS:
        fp = basin_footprints.get(basin, {"lats": [], "lons": []})
        footprint_traces.append({
            "type": "scattergeo",
            "lat": fp["lats"], "lon": fp["lons"],
            "mode": "markers",
            "marker": {"color": BASIN_COLORS[basin], "size": 6, "opacity": 0.12,
                       "symbol": "square"},
            "name": BASIN_NAMES[basin],
            "legendgroup": basin,
            "showlegend": True,
            "hoverinfo": "skip",
        })

    # ── Traces 6-11: storm marker traces (animated) ───────────────────────
    initial_storm_traces = []
    for idx, basin in enumerate(BASINS):
        bd = first_data["basins"].get(basin, {"lats": [], "lons": [], "winds": [], "angles": []})
        initial_storm_traces.append({
            "type": "scattergeo",
            "lat": bd["lats"], "lon": bd["lons"],
            "mode": "markers",
            "name": BASIN_NAMES[basin],
            "marker": _marker_cfg(bd["winds"], bd["angles"]),
            "legendgroup": basin,
            "showlegend": False,   # legend entry provided by footprint trace
            "hovertemplate": (
                f"<b>{BASIN_NAMES[basin]}</b><br>"
                "Wind: %{marker.color:.0f} kt<extra></extra>"
            ),
        })

    # Invisible anchor trace that keeps the wind-speed colorbar always visible.
    # Storm traces can have empty data in quiet months, which makes Plotly drop
    # the colorbar — this static trace prevents that.
    colorbar_anchor = {
        "type": "scattergeo",
        "lat": [0], "lon": [0],
        "mode": "markers",
        "marker": {
            "color": [0],
            "colorscale": WIND_COLORSCALE,
            "cmin": 0, "cmax": 185,
            "size": 0, "opacity": 0,
            "colorbar": {
                "title": {"text": "Wind speed (kt)", "font": {"color": "#c9d1d9", "size": 11}},
                "tickvals": [0, 34, 64, 83, 96, 113, 137],
                "ticktext": ["0 TD", "34 TS", "64 C1", "83 C2", "96 C3", "113 C4", "137 C5"],
                "tickfont": {"color": "#c9d1d9", "size": 9},
                "bgcolor": "#1c2128", "bordercolor": "#30363d",
                "len": 0.5, "x": 1.01,
            },
        },
        "showlegend": False,
        "hoverinfo": "skip",
    }

    initial_traces = [colorbar_anchor] + footprint_traces + initial_storm_traces

    # ── Animation frames ──────────────────────────────────────────────────
    frames = []
    for key in sorted_keys:
        yr         = animation[key]
        frame_data = []
        for idx, basin in enumerate(BASINS):
            bd = yr["basins"].get(basin, {"lats": [], "lons": [], "winds": [], "angles": []})
            frame_data.append({
                "lat": bd["lats"],
                "lon": bd["lons"],
                "marker": _marker_cfg(bd["winds"], bd["angles"]),
            })
        frames.append({
            "name": key,
            "data": frame_data,
            "traces": list(range(N_BASINS + 1, N_BASINS * 2 + 1)),  # +1 for colorbar anchor
            "layout": {
                "annotations": _annotations(
                    yr["year"], yr["month"], yr["enso"], yr["n_storms"]),
                "showlegend": True,   # prevent legend from being hidden on any frame
            },
        })

    # ── Slider ────────────────────────────────────────────────────────────
    slider_steps = []
    for key in sorted_keys:
        yr    = animation[key]
        month = yr["month"]
        year  = yr["year"]
        label = str(year) if month == 1 else ""
        slider_steps.append({
            "args": [[key], {"frame": {"duration": 300, "redraw": True},
                             "mode": "immediate",
                             "transition": {"duration": 100}}],
            "label": label,
            "method": "animate",
        })

    sliders = [{
        "active": 0,
        "steps": slider_steps,
        "x": 0.0, "y": 0, "xanchor": "left", "yanchor": "top", "len": 1.0,
        "currentvalue": {"visible": False},
        "transition": {"duration": 100},
        "bgcolor": "#21262d", "bordercolor": "#30363d",
        "tickcolor": "#8b949e",
        "font": {"color": "#8b949e", "size": 9},
        "pad": {"b": 10, "t": 70},  # 70px above rail leaves room for the buttons
        "minorticklen": 0,
    }]

    # ── Layout ────────────────────────────────────────────────────────────
    layout = {
        "paper_bgcolor": "#0d1117",
        "uirevision": "constant",   # preserves legend show/hide state across animation frames
        "geo": {
            "bgcolor": "#0d1117",
            "showland": True,       "landcolor": "#1c2128",
            "showocean": True,      "oceancolor": "#0d1117",
            "showcoastlines": True, "coastlinecolor": "#444c56",
            "showcountries": True,  "countrycolor": "#30363d",
            "showframe": False,
            "projection": {"type": "natural earth"},
        },
        "margin": {"l": 0, "r": 0, "t": 0, "b": 130},
        "legend": {
            "x": 0.82, "y": 0.98, "xanchor": "left", "yanchor": "top",
            "bgcolor": "#1c2128", "bordercolor": "#30363d", "borderwidth": 1,
            "font": {"color": "#c9d1d9", "size": 11},
        },
        "updatemenus": [{
            "type": "buttons", "showactive": False,
            "x": 0.01, "y": 0.08, "xanchor": "left", "yanchor": "top",
            "buttons": [
                {"label": "▶  Play", "method": "animate",
                 "args": [None, {"frame": {"duration": 400, "redraw": True},
                                 "fromcurrent": True, "mode": "immediate",
                                 "transition": {"duration": 150}}]},
                {"label": "⏸  Pause", "method": "animate",
                 "args": [[None], {"frame": {"duration": 0, "redraw": False},
                                   "mode": "immediate",
                                   "transition": {"duration": 0}}]},
            ],
            "bgcolor": "#1c2128", "bordercolor": "#30363d",
            "font": {"color": "#c9d1d9", "size": 12},
        }],
        "annotations": _annotations(first_data["year"], first_data["month"],
                                     first_data["enso"], first_data["n_storms"]),
        "sliders": sliders,
    }

    # ── Difference map ────────────────────────────────────────────────────
    pts     = diff_map["points"]
    n_en    = diff_map["n_el_nino"]
    n_oth   = diff_map["n_other"]
    max_abs = max((abs(p["diff"]) for p in pts), default=1.0)

    diff_trace = {
        "type": "scattergeo",
        "lat":  [p["lat"]  for p in pts],
        "lon":  [p["lon"]  for p in pts],
        "mode": "markers",
        "marker": {
            "color":      [p["diff"] for p in pts],
            "colorscale": "RdBu_r",
            "cmin": -max_abs, "cmax": max_abs,
            "size": 7, "opacity": 0.85,
            "colorbar": {
                "title": {"text": "Wind intensity·density<br>(El Niño − other, kt·obs/mo)",
                          "font": {"color": "#c9d1d9", "size": 11}},
                "tickfont": {"color": "#c9d1d9"},
                "bgcolor": "#1c2128", "bordercolor": "#30363d",
            },
        },
        "text": [f"{'More' if p['diff']>0 else 'Less'} intense activity during El Niño<br>"
                 f"Δ {p['diff']:+.1f} kt·obs/mo" for p in pts],
        "hovertemplate": "%{text}<extra></extra>",
        "showlegend": False,
    }

    diff_layout = {
        "paper_bgcolor": "#0d1117",
        "geo": {
            "bgcolor": "#0d1117",
            "showland": True,       "landcolor": "#1c2128",
            "showocean": True,      "oceancolor": "#0d1117",
            "showcoastlines": True, "coastlinecolor": "#444c56",
            "showcountries": True,  "countrycolor": "#30363d",
            "showframe": False,
            "projection": {"type": "natural earth"},
        },
        "margin": {"l": 0, "r": 0, "t": 10, "b": 10},
    }

    # ── Serialize ─────────────────────────────────────────────────────────
    traces_json = json.dumps(initial_traces)
    layout_json = json.dumps(layout)
    frames_json = json.dumps(frames)
    diff_t_json = json.dumps([diff_trace])
    diff_l_json = json.dumps(diff_layout)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tropical Cyclone Tracks &amp; ENSO</title>
<script src="https://cdn.plot.ly/plotly-2.30.0.min.js" charset="utf-8"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0d1117; color: #c9d1d9;
          font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
          padding: 1.5rem; }}
  h1 {{ font-size: 1.4rem; font-weight: 700; margin-bottom: 0.2rem; }}
  .subtitle {{ color: #8b949e; font-size: 0.85rem; margin-bottom: 1.5rem; }}
  .subtitle a {{ color: #58a6ff; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
           padding: 1rem; margin-bottom: 1.5rem; }}
  .card h2 {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: .05em;
              color: #8b949e; margin-bottom: 0.8rem; }}
  .enso-key {{ display: flex; gap: 1.5rem; font-size: 0.8rem; margin-bottom: 0.6rem; }}
  .en {{ color: #ff6b35; font-weight: 600; }}
  .ln {{ color: #4a9eff; font-weight: 600; }}
  .nt {{ color: #8b949e; font-weight: 600; }}
  .wind-key {{ display: flex; gap: 0.8rem; font-size: 0.75rem; margin-bottom: 0.5rem;
               flex-wrap: wrap; }}
  .wind-key span {{ padding: 1px 7px; border-radius: 3px; font-weight: 600; }}
  footer {{ font-size: 0.75rem; color: #8b949e; margin-top: 1rem; text-align: center; }}
  footer a {{ color: #8b949e; }}
  .note {{ font-size: 0.75rem; color: #8b949e; margin-bottom: 0.6rem; line-height: 1.5; }}
  .topnav {{ display:flex; align-items:center; justify-content:space-between; padding:.5rem 0; border-bottom:1px solid #30363d; margin-bottom:1.2rem; }}
  .nav-brand {{ font-weight:700; font-size:.95rem; color:#c9d1d9; text-decoration:none; }}
  .nav-links {{ display:flex; gap:.4rem; }}
  .nav-links a {{ color:#8b949e; text-decoration:none; font-size:.82rem; padding:.3rem .7rem; border-radius:5px; }}
  .nav-links a:hover {{ color:#c9d1d9; background:#161b22; }}
  .nav-links a.nav-active {{ color:#fff; background:#e74c3c; font-weight:600; }}
</style>
</head>
<body>
<nav class="topnav">
  <a class="nav-brand" href="index.html">ENSO Tracker</a>
  <div class="nav-links">
    <a href="index.html">ENSO Dashboard</a>
    <a href="hurricanes.html" class="nav-active">Cyclone Tracker</a>
    <a href="precipitation.html">Precipitation</a>
    <a href="temperature.html">Temperature</a>
  </div>
</nav>
<h1>Global Tropical Cyclone Tracks &amp; ENSO</h1>
<p class="subtitle">
  IBTrACS best-track data across all 6 ocean basins ·
  El Niño / La Niña years classified by NOAA/CPC ONI (ASO season, threshold ±0.5 °C) ·
  Sources: <a href="https://www.ncdc.noaa.gov/ibtracs/" target="_blank">IBTrACS</a> &amp;
  <a href="https://www.cpc.ncep.noaa.gov/" target="_blank">NOAA/CPC</a>
</p>

<div class="card">
  <h2>Tropical Cyclone Tracks by Year — All Basins</h2>
  <div class="enso-key">
    <span class="en">● El Niño year</span>
    <span class="ln">● La Niña year</span>
    <span class="nt">● Neutral year</span>
  </div>
  <div class="wind-key">
    <span style="background:#5ebaff;color:#000">TD &lt;34 kt</span>
    <span style="background:#00faf4;color:#000">TS 34–63 kt</span>
    <span style="background:#ffffcc;color:#333">Cat 1 64–82 kt</span>
    <span style="background:#ffe775;color:#333">Cat 2 83–95 kt</span>
    <span style="background:#ffc140;color:#000">Cat 3 96–112 kt</span>
    <span style="background:#ff8f20;color:#000">Cat 4 113–136 kt</span>
    <span style="background:#ff6060;color:#fff">Cat 5 ≥137 kt</span>
  </div>
  <p class="note">Dot colour = wind speed (Saffir-Simpson scale). Shaded regions = basin boundaries.
  Use ▶ Play to animate, or drag the slider.</p>
  <div id="animDiv" style="height:540px"></div>
</div>

<div class="card">
  <h2>Track Density Difference — El Niño ({n_en} months) vs All Other ({n_oth} months)</h2>
  <p class="note">
    Each 2.5° × 2.5° cell shows wind-weighted storm activity (each observation contributes
    its wind speed in kt, so intense storms count more than weak ones), averaged per year,
    differenced between El Niño and all other years (La Niña + Neutral).
    <span style="color:#e74c3c">Red</span> = more intense activity during El Niño ·
    <span style="color:#4a9eff">Blue</span> = less intense activity during El Niño.
  </p>
  <div id="diffDiv" style="height:480px"></div>
</div>

<footer>
  Track data: <a href="https://www.ncdc.noaa.gov/ibtracs/" target="_blank">IBTrACS</a>
  (NOAA/NCEI best-track archive) ·
  ENSO classification: <a href="https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt" target="_blank">NOAA/CPC ONI</a>
  &nbsp;·&nbsp; <a href="precipitation.html">🌧 Precipitation →</a>
  &nbsp;·&nbsp; <a href="temperature.html">🌡 Temperature →</a>
</footer>

<script>
(function() {{
  const el = document.getElementById('animDiv');
  const traces = {traces_json};
  const layout = {layout_json};
  const frames = {frames_json};
  Plotly.newPlot(el, traces, layout, {{responsive: true, displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d','select2d']}})
    .then(() => Plotly.addFrames(el, frames));
}})();

(function() {{
  const el = document.getElementById('diffDiv');
  Plotly.newPlot(el, {diff_t_json}, {diff_l_json},
    {{responsive: true, displaylogo: false,
      modeBarButtonsToRemove: ['lasso2d','select2d']}});
}})();
</script>
</body>
</html>"""

    with open(output, "w") as f:
        f.write(html)
    print(f"Hurricane page written → {output}")


if __name__ == "__main__":
    from fetch_hurricanes import fetch_hurricane_data
    data = fetch_hurricane_data()
    render_hurricanes(data)
