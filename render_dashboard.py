"""
render_dashboard.py
Takes the data dict from fetch_enso.py and writes a self-contained HTML dashboard.
No external dependencies — pure Python stdlib + inline JS/CSS.
"""

import json
import os


def classify(nino34_anom: float) -> tuple[str, str]:
    """Returns (label, css-color-variable) based on Niño-3.4 anomaly."""
    if nino34_anom >= 2.0:
        return "Super El Niño", "#b22222"
    elif nino34_anom >= 1.5:
        return "Strong El Niño", "#d4380d"
    elif nino34_anom >= 1.0:
        return "Moderate El Niño", "#fa8c16"
    elif nino34_anom >= 0.5:
        return "Weak El Niño", "#faad14"
    elif nino34_anom <= -1.5:
        return "Strong La Niña", "#003a8c"
    elif nino34_anom <= -1.0:
        return "Moderate La Niña", "#1d39c4"
    elif nino34_anom <= -0.5:
        return "Weak La Niña", "#2f54eb"
    else:
        return "ENSO-Neutral", "#389e0d"


def impacts_for(label: str) -> list[str]:
    """Regional impact bullets for current ENSO state."""
    el_nino = [
        "SW United States & California: Above-normal precipitation likely Nov–Mar",
        "Gulf Coast: Enhanced flood and tornado risk through spring",
        "Pacific Northwest & Great Lakes: Warmer, drier winter typical",
        "Colorado River Basin: Improved reservoir recharge potential",
        "Atlantic Hurricane Season: Suppressed activity expected",
        "Australia / SE Asia: Drought risk, elevated wildfire danger",
        "Horn of Africa: Above-normal rainfall, flooding risk",
        "Peru / Ecuador: Extreme coastal rainfall and flooding",
    ]
    la_nina = [
        "SW United States: Drier-than-normal winter, drought risk",
        "Pacific Northwest & Great Lakes: Cooler, wetter winter typical",
        "Gulf Coast: Below-normal precipitation, mild hurricane season impact",
        "Australia / SE Asia: Enhanced monsoon, flooding risk",
        "Horn of Africa: Below-normal rainfall, drought risk",
        "Atlantic Hurricane Season: Enhanced activity expected",
        "Brazil: Reduced rainfall in NE, flooding in S",
    ]
    neutral = [
        "No dominant ENSO-driven signal; regional variability dominates",
        "Monitor for potential transition to El Niño or La Niña",
    ]
    if "El Niño" in label:
        return el_nino
    elif "La Niña" in label:
        return la_nina
    return neutral


def render(data: dict, output_path: str = "docs/index.html") -> None:
    weekly = data.get("weekly_history", [])
    oni_h  = data.get("oni_history", [])
    roni_h = data.get("roni_history", [])
    lw     = data.get("latest_weekly", {})
    lo     = data.get("latest_oni", {})
    lr     = data.get("latest_roni", {})
    disc   = data.get("discussion", {})
    fetched = data.get("fetched_utc", "")[:10]

    anom = lw.get("nino34_anom", 0.0)
    label, color = classify(anom)
    impacts = impacts_for(label)

    # NOAA/CPC chart data
    weekly_dates  = [r["date"] for r in weekly]
    weekly_anoms  = [r["nino34_anom"] for r in weekly]
    oni_labels    = [f"{r['season']} {r['year']}" for r in oni_h]
    oni_values    = [r["oni"] for r in oni_h]
    roni_labels   = [
        f"{r.get('season', r.get('month',''))} {r['year']}" for r in roni_h
    ]
    roni_values   = [r["roni"] for r in roni_h]

    impact_li = "\n".join(f"<li>{i}</li>" for i in impacts)
    status_badge = disc.get("status", "Unknown")
    synopsis = disc.get("synopsis", "").replace("<", "&lt;").replace(">", "&gt;")
    issued   = disc.get("issued", "")

    # IRI data
    iri_imgs     = data.get("iri_images", {})
    iri_strength = data.get("iri_strength") or {}
    sp_seasons   = iri_strength.get("seasons", [])
    sp_traces    = iri_strength.get("traces", [])
    sp_title     = iri_strength.get("title", "ENSO Strength Categories")

    # Build Chart.js datasets for strength stacked bar
    # Note: borderRadius must NOT be set on stacked bar datasets in Chart.js 4 — it makes segments invisible
    strength_datasets = json.dumps([
        {
            "label":           t["name"],
            "data":            t["y"],
            "backgroundColor": t["color"],
            "borderWidth":     0,
        }
        for t in sp_traces
    ])

    img_cpc       = iri_imgs.get("cpc_probs", "")
    img_sst_hist  = iri_imgs.get("iri_sst_history", "")
    img_iri_probs = iri_imgs.get("iri_probs", "")

    # SST model predictions (from Playwright Highcharts extraction)
    import hashlib
    from collections import defaultdict

    SEASON_ORDER = ["MAM-OBS","May-OBS","MJJ","JJA","JAS","ASO","SON","OND","NDJ","DJF","JFM","FMA","MAM","AMJ"]
    AVG_SERIES   = {"DYN AVG", "STAT AVG", "REL AVG"}  # stripped — .strip() removes trailing space
    OBS_SERIES   = {"Observed"}

    model_preds = data.get("iri_model_predictions") or []

    # Group: model → season → [values]  (multiple runs → average)
    raw: dict = defaultdict(lambda: defaultdict(list))
    for rec in model_preds:
        m = (rec.get("model") or "").strip()
        s = (rec.get("season") or "").strip()
        v = rec.get("nino34_anomaly")
        if m and s and v is not None:
            raw[m][s].append(float(v))

    # Average duplicates, filtering NaN/None
    pred_by_model: dict = {}
    for m, sdict in raw.items():
        pred_by_model[m] = {}
        for s, vs in sdict.items():
            clean_vs = [v for v in vs if v is not None and v == v]  # v!=v catches NaN
            pred_by_model[m][s] = round(sum(clean_vs)/len(clean_vs), 3) if clean_vs else None

    # Determine season order from data (only seasons present)
    all_seasons_in_data = {s for sdict in pred_by_model.values() for s in sdict}
    pred_seasons = [s for s in SEASON_ORDER if s in all_seasons_in_data]
    # Add any remaining not in our ordered list
    pred_seasons += [s for s in sorted(all_seasons_in_data) if s not in pred_seasons]

    # ── Model type classification ────────────────────────────────────────────
    DYNAMICAL_MODELS = {
        "NCEP CFSv2","NASA GMAOv3","GFDL SPEAR","ECMWF","JMA","UKMO",
        "MetFRANCE","DWD","CMC CANSIP","KMA","BCC_CSM11m","AUS-ACCESS",
        "SINTEX-F","IOCAS ICM","CMCC-SPS4","COLA CCSM4","JAMSTEC CNN",
        "NTU CODA","UW PSL-CSLIM","CS-IRI-MM","BCC DIAP",
    }
    STATISTICAL_MODELS = {
        "CPC CA","CPC MRKOV","CSU CLIPR","LDEO","BCC_RZDM",
        "IAP-NN","XRO","UCLA-TCD",
    }
    RELATIVE_MODELS = {"AUS-RELATIVE","CMCC RELATIVE","UW PSL-LIM"}

    def _mtype(name):
        if name in DYNAMICAL_MODELS: return "dyn"
        if name in STATISTICAL_MODELS: return "stat"
        if name in RELATIVE_MODELS: return "rel"
        return "dyn"  # OBS-N and unknowns → treat as dynamical runs

    # Type visual config
    TYPE_CFG = {
        "dyn":  {"symbol": "circle",        "opacity": 0.75, "size": 5,
                 "legend_label": "Dynamical Models",   "legend_symbol": "circle"},
        "stat": {"symbol": "circle-open",   "opacity": 0.85, "size": 6,
                 "legend_label": "Statistical Models", "legend_symbol": "circle-open"},
        "rel":  {"symbol": "diamond-open",  "opacity": 0.85, "size": 6,
                 "legend_label": "Relative Models",    "legend_symbol": "diamond-open"},
    }
    # Distinct, highly separated colors for the three averages + observed
    AVG_COLORS = {
        "DYN AVG":  {"line": "#f5a623", "marker": "star",        "width": 3.5, "size": 10},
        "STAT AVG": {"line": "#00e5ff", "marker": "star-square",  "width": 3.5, "size": 10},
        "REL AVG":  {"line": "#e040fb", "marker": "star-diamond", "width": 3.5, "size": 10},
    }

    # Sort models: dyn → stat → rel alphabetically within each group
    def _sort_key(name):
        order = {"dyn": 0, "stat": 1, "rel": 2}
        return (order[_mtype(name)], name)

    forecast_model_names = sorted(
        (m for m, sv in pred_by_model.items()
         if m not in OBS_SERIES and m not in AVG_SERIES
         and any(v is not None for v in [sv.get(s) for s in pred_seasons])),
        key=_sort_key,
    )

    # Per-type color index counters for hue rotation within each band
    type_counts = {"dyn": 0, "stat": 0, "rel": 0}
    type_totals = {t: sum(1 for m in forecast_model_names if _mtype(m) == t)
                   for t in ("dyn","stat","rel")}

    def _mcolor(name):
        mt = _mtype(name)
        idx = type_counts[mt]
        n   = max(type_totals[mt], 1)
        type_counts[mt] += 1
        if mt == "dyn":
            hue = int(idx * 85 / n)        # 0–85°  reds/oranges/yellows
        elif mt == "stat":
            hue = 155 + int(idx * 85 / n)  # 155–240° greens/cyans/blues
        else:
            hue = 265 + int(idx * 50 / n)  # 265–315° purples/magentas
        return f"hsl({hue},75%,62%)"

    # ── Build Plotly traces ───────────────────────────────────────────────
    plume_traces_list = []
    trace_types: list = []   # parallel type-tag list for updatemenus visibility

    # 1. Individual model lines (below averages in z-order)
    for mname in forecast_model_names:
        mt    = _mtype(mname)
        cfg   = TYPE_CFG[mt]
        color = _mcolor(mname)
        row   = [pred_by_model[mname].get(s) for s in pred_seasons]
        plume_traces_list.append({
            "type": "scatter", "x": pred_seasons, "y": row,
            "mode": "lines+markers", "name": mname,
            "legendgroup": mt, "showlegend": False,
            "connectgaps": True, "opacity": cfg["opacity"],
            "line":   {"color": color, "width": 1.5},
            "marker": {"color": color, "size": cfg["size"],
                       "symbol": cfg["symbol"],
                       "line": {"color": color, "width": 1.5}},
            "hovertemplate": f"<b>{mname}</b> ({mt.upper()})<br>%{{x}}: %{{y:.2f}} °C<extra></extra>",
        })
        trace_types.append(mt)

    # 2. Dummy legend entries for each present model type
    for mt, cfg in TYPE_CFG.items():
        n_mt = type_totals[mt]
        if n_mt == 0:
            continue
        dummy_color = {"dyn": "#fa8c16", "stat": "#40c4ff", "rel": "#ce93d8"}[mt]
        plume_traces_list.append({
            "type": "scatter", "x": [None], "y": [None],
            "mode": "markers+lines", "name": f"{cfg['legend_label']} (N={n_mt})",
            "legendgroup": mt, "showlegend": True,
            "line": {"color": dummy_color, "width": 1.5},
            "marker": {"color": dummy_color, "size": 8,
                       "symbol": cfg["legend_symbol"],
                       "line": {"color": dummy_color, "width": 1.5}},
        })
        trace_types.append(f"dummy_{mt}")

    # 3. Ensemble averages (rendered on top)
    avg_order = ["DYN AVG", "STAT AVG", "REL AVG"]
    for mname in avg_order:
        if mname not in pred_by_model:
            continue
        cfg  = AVG_COLORS[mname]
        row  = [pred_by_model[mname].get(s) for s in pred_seasons]
        plume_traces_list.append({
            "type": "scatter", "x": pred_seasons, "y": row,
            "mode": "lines+markers", "name": mname,
            "legendgroup": "avg", "showlegend": True,
            "connectgaps": True,
            "line":   {"color": cfg["line"], "width": cfg["width"]},
            "marker": {"color": cfg["line"], "size": cfg["size"],
                       "symbol": cfg["marker"],
                       "line": {"color": "#fff", "width": 1}},
            "hovertemplate": f"<b>{mname}</b><br>%{{x}}: %{{y:.2f}} °C<extra></extra>",
        })
        trace_types.append(f"avg_{mname}")

    # 4. Observed (dashed blue, rendered last so it's always on top)
    for mname in sorted(m for m in pred_by_model if m in OBS_SERIES):
        row = [pred_by_model[mname].get(s) for s in pred_seasons]
        plume_traces_list.append({
            "type": "scatter", "x": pred_seasons, "y": row,
            "mode": "lines+markers", "name": mname,
            "legendgroup": "obs", "showlegend": True,
            "connectgaps": True,
            "line":   {"color": "#58a6ff", "width": 2.5, "dash": "dot"},
            "marker": {"color": "#58a6ff", "size": 7, "symbol": "circle-dot"},
            "hovertemplate": f"<b>{mname}</b><br>%{{x}}: %{{y:.2f}} °C<extra></extra>",
        })
        trace_types.append("obs")

    # ── Dropdown updatemenus ──────────────────────────────────────────────
    def _vis(show_tags):
        return [True if t in show_tags else "legendonly" for t in trace_types]

    all_tags     = set(trace_types)
    avg_tags     = {t for t in all_tags if t.startswith("avg_")}
    dummy_tags   = {t for t in all_tags if t.startswith("dummy_")}
    dyn_tags     = {"dyn", "dummy_dyn"} | {t for t in avg_tags if "DYN" in t}
    stat_tags    = {"stat", "dummy_stat"} | {t for t in avg_tags if "STAT" in t}
    rel_tags     = {"rel", "dummy_rel"} | {t for t in avg_tags if "REL" in t}
    avg_only_tags = avg_tags | dummy_tags | {"obs"}

    dropdown_menu = {
        "buttons": [
            {"label": "All Models",        "method": "restyle",
             "args": [{"visible": _vis(all_tags)}]},
            {"label": "Dynamical Only",    "method": "restyle",
             "args": [{"visible": _vis(dyn_tags | {"obs"})}]},
            {"label": "Statistical Only",  "method": "restyle",
             "args": [{"visible": _vis(stat_tags | {"obs"})}]},
            {"label": "Relative Only",     "method": "restyle",
             "args": [{"visible": _vis(rel_tags | {"obs"})}]},
            {"label": "Averages Only",     "method": "restyle",
             "args": [{"visible": _vis(avg_only_tags)}]},
        ],
        "direction": "down", "showactive": True, "type": "dropdown",
        "x": 0.0, "y": 1.08, "xanchor": "left", "yanchor": "top",
        "bgcolor": "#1c2128", "bordercolor": "#58a6ff", "borderwidth": 1,
        "font": {"color": "#c9d1d9", "size": 12},
        "pad": {"r": 10, "t": 5},
        "active": 0,
    }

    plume_traces_json = json.dumps(plume_traces_list)
    has_plume         = bool(plume_traces_list)

    plume_layout_json = json.dumps({
        "paper_bgcolor": "#161b22", "plot_bgcolor": "#0d1117",
        "margin": {"l": 60, "r": 30, "t": 60, "b": 80},
        "font": {"color": "#c9d1d9",
                 "family": "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"},
        "xaxis": {"gridcolor": "#21262d", "linecolor": "#30363d",
                  "tickfont": {"color": "#8b949e", "size": 12}, "tickangle": -30},
        "yaxis": {"title": "Niño-3.4 Anomaly (°C)",
                  "titlefont": {"color": "#8b949e", "size": 12},
                  "gridcolor": "#21262d", "linecolor": "#30363d",
                  "tickfont": {"color": "#8b949e", "size": 11}, "ticksuffix": " °C",
                  "zeroline": True, "zerolinecolor": "#444", "zerolinewidth": 1},
        "legend": {"bgcolor": "#1c2128", "bordercolor": "#30363d", "borderwidth": 1,
                   "font": {"color": "#c9d1d9", "size": 12},
                   "x": 1.01, "y": 1, "xanchor": "left", "yanchor": "top"},
        "hovermode": "closest",
        "hoverlabel": {"bgcolor": "#1c2128", "bordercolor": "#30363d",
                       "font": {"color": "#c9d1d9", "size": 13}},
        "updatemenus": [dropdown_menu],
    })

    # Plotly traces for the strength stacked bar
    sp_model_counts = iri_strength.get("model_counts", [])
    strength_traces_list = []
    for t in sp_traces:
        texts, counts = [], []
        for si, pct_val in enumerate(t["y"]):
            n = sp_model_counts[si] if si < len(sp_model_counts) else 26
            c = round(pct_val * n / 100)
            counts.append(c)
            texts.append(str(c) if c >= 2 else "")
        strength_traces_list.append({
            "type": "bar", "name": t["name"], "x": sp_seasons, "y": t["y"],
            "text": texts, "textposition": "inside", "insidetextanchor": "middle",
            "textfont": {"size": 15, "color": "white", "family": "Arial Black, sans-serif"},
            "marker": {"color": t["color"]},
            "customdata": counts,
            "hovertemplate": "<b>%{fullData.name}</b><br>Season: %{x}<br>%{y:.0f}% (%{customdata} models)<extra></extra>",
        })

    strength_traces_json = json.dumps(strength_traces_list)
    strength_layout_json = json.dumps({
        "barmode": "stack",
        "paper_bgcolor": "#161b22", "plot_bgcolor": "#161b22",
        "margin": {"l": 55, "r": 20, "t": 10, "b": 160},
        "font": {"color": "#c9d1d9", "family": "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"},
        "xaxis": {"title": "Season", "titlefont": {"color": "#8b949e", "size": 12},
                  "gridcolor": "#21262d", "linecolor": "#30363d",
                  "tickfont": {"color": "#8b949e", "size": 13}},
        "yaxis": {"title": "% of Models", "titlefont": {"color": "#8b949e", "size": 12},
                  "range": [0, 100], "gridcolor": "#21262d", "linecolor": "#30363d",
                  "tickfont": {"color": "#8b949e", "size": 11}, "ticksuffix": "%"},
        "legend": {"orientation": "h", "y": -0.25, "x": 0.5, "xanchor": "center",
                   "bgcolor": "rgba(0,0,0,0)", "font": {"color": "#c9d1d9", "size": 11}},
        "hoverlabel": {"bgcolor": "#1c2128", "bordercolor": "#30363d",
                       "font": {"color": "#c9d1d9", "size": 12}},
    })

    has_strength = bool(strength_traces_list)

    # Gauge needle angle: maps -3..+3 anomaly → -90°..+90°
    needle_deg = max(-90, min(90, anom / 3.0 * 90))

    def _tip(text):
        return f'<span class="info-icon"><span class="tip">{text}</span></span>'

    TIP_STATE    = _tip("The Niño-3.4 region (5°N–5°S, 170°W–120°W) SST anomaly is the primary ENSO index. Values above +0.5 °C indicate El Niño; below −0.5 °C indicate La Niña. This weekly reading comes from NOAA/CPC's Reynolds OI SST file (wksst9120.for), using a 1991–2020 climatological base period.")
    TIP_GAUGE    = _tip("Visual indicator of ENSO phase and intensity. The needle maps the current Niño-3.4 anomaly to ±0.5 °C (weak), ±1.0 °C (moderate), ±1.5 °C (strong), and ±2.0 °C (very strong) thresholds. ONI and RONI below are 3-month running means.")
    TIP_ADVISORY = _tip("The official NOAA/CPC ENSO Diagnostic Discussion, issued monthly. An El Niño or La Niña Advisory is declared when the Oceanic Niño Index (ONI) meets or exceeds ±0.5 °C for five consecutive overlapping 3-month seasons.")
    TIP_WEEKLY   = _tip("Weekly Niño-3.4 SST anomaly over the past 52 weeks, from NOAA/CPC's Reynolds OI SST file (wksst9120.for, base period 1991–2020). Dashed lines at ±0.5 °C mark the boundary between ENSO phases.")
    TIP_ONI      = _tip("ONI (Oceanic Niño Index) is the standard 3-month running mean of the Niño-3.4 anomaly — the primary metric NOAA uses to classify El Niño and La Niña events. RONI (Relative ONI) applies a linear detrending to remove the long-term warming signal.")
    TIP_IMPACTS  = _tip("Typical regional climate impacts associated with the current ENSO phase, based on historical composites from NOAA/CPC. Actual impacts vary by location, season, and event intensity.")
    TIP_FIG1     = _tip("CPC's probabilistic forecast showing the likelihood of El Niño, Neutral, and La Niña conditions for each upcoming season, based on a consolidation of dynamical and statistical model guidance.")
    TIP_FIG2     = _tip("Historical time series of observed Niño-3.4 SST anomalies, providing context for how the current state compares with recent years.")
    TIP_FIG3     = _tip("IRI's probabilistic ENSO forecast, blending output from multiple dynamical models, statistical models, and expert judgment. Issued mid-month.")
    TIP_PLUME    = _tip("Each line is one model's Niño-3.4 anomaly forecast. ● Filled circles = dynamical models: physics-based coupled ocean–atmosphere GCMs that simulate fluid equations (e.g. ECMWF, NCEP CFSv2). ○ Open circles = statistical models: data-driven methods trained on historical SST patterns (e.g. CPC CA, LDEO). ◇ Open diamonds = relative models: IRI's third category, including linear inverse models and statistical post-processing of dynamical output (IRI does not formally define this group on their site). Stars = ensemble averages per type. Use the dropdown to filter.")
    TIP_STRENGTH = _tip("Stacked bar chart showing the percentage of IRI models predicting each ENSO strength category (Very Strong La Niña through Very Strong El Niño) for each upcoming season. Numbers inside bars show the model count. Taller red bars indicate stronger El Niño consensus.")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ENSO Tracker — {fetched}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
<script src="https://cdn.plot.ly/plotly-2.30.0.min.js" charset="utf-8"></script>
<style>
  :root {{
    --accent: {color};
    --bg: #0d1117;
    --card: #161b22;
    --border: #30363d;
    --text: #c9d1d9;
    --muted: #8b949e;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; padding: 1.5rem; }}
  h1 {{ font-size: 1.4rem; font-weight: 700; margin-bottom: 0.2rem; }}
  .subtitle {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 1.5rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }}
  .card h2 {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin-bottom: 0.6rem; }}
  .big-num {{ font-size: 2.4rem; font-weight: 700; color: var(--accent); line-height: 1; }}
  .label {{ font-size: 1rem; font-weight: 600; color: var(--accent); margin-top: 0.3rem; }}
  .badge {{ display: inline-block; background: var(--accent); color: #fff; border-radius: 4px; padding: 0.15rem 0.5rem; font-size: 0.78rem; font-weight: 700; margin-bottom: 0.5rem; }}
  .row {{ display: flex; gap: 0.5rem; align-items: baseline; }}
  .row span {{ font-size: 0.8rem; color: var(--muted); }}
  /* Gauge — half-circle with linear gradient, stops sin()-mapped so needle tip matches zone */
  /* At anomaly A°C: needle angle = A/3*90°, tip x-pos = 50% + sin(angle)*50%             */
  /* ±0.5→63/37%, ±1.0→75/25%, ±1.5→85/15%, ±2.0→93/7%                                   */
  .gauge-wrap {{ display: flex; flex-direction: column; align-items: center; }}
  .gauge {{ width: 160px; height: 80px; position: relative; }}
  .gauge-arc {{ width: 160px; height: 80px; border-radius: 80px 80px 0 0; background: linear-gradient(to right,
    #003a8c 0%,
    #1d39c4 15%,
    #2f54eb 25%,
    #389e0d 37%,
    #389e0d 63%,
    #faad14 63%,
    #fa8c16 75%,
    #d4380d 85%,
    #b22222 93%,
    #b22222 100%
  ); }}
  .gauge-needle {{ position: absolute; bottom: 0; left: 50%; width: 2px; height: 74px; background: white; transform-origin: bottom center; transform: rotate({needle_deg}deg); border-radius: 2px; }}
  .gauge-label {{ font-size: 0.72rem; color: var(--muted); margin-top: 0.4rem; display: flex; justify-content: space-between; width: 160px; }}
  /* Chart */
  .chart-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }}
  .chart-card h2 {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin-bottom: 0.8rem; }}
  canvas {{ max-height: 220px; }}
  /* Impacts */
  .impacts ul {{ list-style: disc; padding-left: 1.2rem; }}
  .impacts li {{ font-size: 0.85rem; margin-bottom: 0.35rem; line-height: 1.4; }}
  /* Synopsis */
  .synopsis {{ font-size: 0.82rem; line-height: 1.55; color: var(--text); }}
  /* IRI figures */
  .section-heading {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: .08em;
    color: var(--muted); margin: 1.8rem 0 0.8rem; border-bottom: 1px solid var(--border);
    padding-bottom: 0.4rem; }}
  .fig-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1rem; margin-bottom: 1rem; }}
  .fig-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    overflow: hidden; }}
  .fig-card img {{ width: 100%; display: block; }}
  .fig-caption {{ font-size: 0.75rem; color: var(--muted); padding: 0.5rem 0.75rem; }}
  .fig-card .img-placeholder {{ background: #1c2128; height: 180px; display: flex;
    align-items: center; justify-content: center; color: var(--muted); font-size: 0.8rem; }}
  /* Footer */
  footer {{ font-size: 0.75rem; color: var(--muted); margin-top: 1.5rem; text-align: center; }}
  footer a {{ color: var(--muted); }}
  /* Info tooltips */
  .info-icon {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 13px; height: 13px; border-radius: 50%;
    border: 1px solid var(--muted); color: var(--muted);
    font-size: 8px; font-style: italic; font-weight: 700;
    cursor: pointer; margin-left: 6px; vertical-align: middle;
    position: relative; flex-shrink: 0;
    text-transform: none; letter-spacing: 0;
  }}
  .info-icon::before {{ content: 'i'; }}
  .info-icon .tip {{
    display: none; position: absolute;
    bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%);
    background: #1c2128; border: 1px solid #444c56; border-radius: 6px;
    padding: 9px 12px; font-size: 0.75rem; line-height: 1.55;
    color: #c9d1d9; width: 260px; z-index: 200; text-align: left;
    font-style: normal; font-weight: 400; pointer-events: none;
    box-shadow: 0 4px 16px rgba(0,0,0,0.5); white-space: normal;
  }}
  .info-icon .tip::after {{
    content: ''; position: absolute; top: 100%; left: 50%;
    transform: translateX(-50%);
    border: 5px solid transparent; border-top-color: #444c56;
  }}
  .info-icon:hover .tip, .info-icon.active .tip {{ display: block; }}
  /* Flip tooltip below when icon is near the top of the viewport */
  .info-icon.tip-below .tip {{
    bottom: auto; top: calc(100% + 8px);
  }}
  .info-icon.tip-below .tip::after {{
    top: auto; bottom: 100%;
    border-top-color: transparent; border-bottom-color: #444c56;
  }}
</style>
</head>
<body>

<h1>ENSO Tracker</h1>
<p class="subtitle">Updated {fetched} · Sources: <a href="https://www.cpc.ncep.noaa.gov/" target="_blank" style="color:#58a6ff">NOAA/CPC</a> &amp; <a href="https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/" target="_blank" style="color:#58a6ff">IRI</a></p>

<div class="grid">
  <!-- Current State -->
  <div class="card">
    <h2>Current State {TIP_STATE}</h2>
    <span class="badge">{status_badge}</span>
    <div class="big-num">{anom:+.2f} °C</div>
    <div class="label">{label}</div>
    <div class="row" style="margin-top:.6rem">
      <span>Niño-3.4 SST anomaly (weekly)</span>
    </div>
  </div>

  <!-- Gauge -->
  <div class="card">
    <h2>Anomaly Gauge {TIP_GAUGE}</h2>
    <div class="gauge-wrap">
      <div class="gauge">
        <div class="gauge-arc"></div>
        <div class="gauge-needle"></div>
      </div>
      <div class="gauge-label"><span>La Niña</span><span>Neutral</span><span>El Niño</span></div>
    </div>
    <div style="margin-top:.8rem">
      <div class="row"><strong>ONI</strong>&nbsp;<span>{lo.get('oni','—')} ({lo.get('season','')} {lo.get('year','')})</span></div>
      <div class="row"><strong>RONI</strong>&nbsp;<span>{lr.get('roni','—')} ({lr.get('season', lr.get('month',''))} {lr.get('year','')})</span></div>
    </div>
  </div>

  <!-- Advisory -->
  <div class="card">
    <h2>CPC Advisory {TIP_ADVISORY}</h2>
    {f'<p style="font-size:.78rem;color:var(--muted);margin-bottom:.5rem">Issued: {issued}</p>' if issued else ''}
    <p class="synopsis">{synopsis or "Diagnostic Discussion not yet available for this week."}</p>
  </div>
</div>

<!-- Weekly anomaly chart -->
<div class="chart-card">
  <h2>Niño-3.4 Weekly Anomaly — Last 52 Weeks {TIP_WEEKLY}</h2>
  <canvas id="weeklyChart"></canvas>
</div>

<!-- ONI vs RONI chart -->
<div class="chart-card">
  <h2>ONI vs RONI — Last 3 Years (Monthly) {TIP_ONI}</h2>
  <canvas id="oniChart"></canvas>
</div>

<!-- Impacts -->
<div class="card impacts" style="margin-bottom:1rem">
  <h2>Regional Impacts — {label} {TIP_IMPACTS}</h2>
  <ul>{impact_li}</ul>
</div>

<!-- ── IRI Forecast Figures ────────────────────────────────────────── -->
<p class="section-heading">IRI / CPC Forecast Figures</p>

<div class="fig-grid">
  <div class="fig-card">
    <img src="{img_cpc}" alt="CPC ENSO Probability Forecast"
         onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
    <div class="img-placeholder" style="display:none">Figure unavailable</div>
    <p class="fig-caption">Figure 1 — CPC ENSO Probability Forecast {TIP_FIG1}</p>
  </div>
  <div class="fig-card">
    <img src="{img_sst_hist}" alt="IRI Historical SST Anomaly"
         onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
    <div class="img-placeholder" style="display:none">Figure unavailable</div>
    <p class="fig-caption">Figure 2 — Niño-3.4 Historical SST Anomaly {TIP_FIG2}</p>
  </div>
  <div class="fig-card">
    <img src="{img_iri_probs}" alt="IRI ENSO Probability Forecast"
         onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
    <div class="img-placeholder" style="display:none">Figure unavailable</div>
    <p class="fig-caption">Figure 3 — IRI ENSO Probability Forecast {TIP_FIG3}</p>
  </div>
</div>

<!-- SST Model Plume -->
<div class="chart-card" style="margin-bottom:1rem">
  <h2>Figure 4 — IRI SST Model Forecast Plume (Niño-3.4 Anomaly) {TIP_PLUME}</h2>
  <p style="font-size:0.75rem;color:var(--muted);margin-bottom:0.8rem">
    Individual model forecasts coloured by model — hover any line to see its name and value.
    Ensemble averages and observed (dashed blue) are labelled in the legend.
  </p>
  {'<div id="plumeDiv" style="height:480px"></div>' if has_plume else
   '<p style="color:var(--muted);font-size:.82rem">Model prediction data unavailable — install playwright to enable.</p>'}
</div>

<!-- Strength Categories -->
<div class="chart-card" style="margin-bottom:1rem">
  <h2>{sp_title} {TIP_STRENGTH}</h2>
  <p style="font-size:0.75rem;color:var(--muted);margin-bottom:0.8rem">
    Percentage of IRI models predicting each ENSO strength category per season.
    Numbers inside bars show model count. Hover for details.
  </p>
  {'<div id="strengthDiv" style="height:480px"></div>' if has_strength else
   '<p style="color:var(--muted);font-size:.82rem">Strength data unavailable.</p>'}
</div>

<footer>
  Data: <a href="https://www.cpc.ncep.noaa.gov/" target="_blank">NOAA/CPC</a> &amp; <a href="https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/" target="_blank">IRI</a>
</footer>

<script>
// Register datalabels globally; set display:false as the default so it only activates
// on charts that explicitly opt in (strength chart overrides to a display function).
Chart.register(ChartDataLabels);
Chart.defaults.plugins.datalabels = {{ display: false }};
const chartDefaults = {{
  plugins: {{
    legend:     {{ labels: {{ color: '#8b949e', font: {{ size: 11 }} }} }},
    datalabels: {{ display: false }},   // off for all charts unless overridden
  }},
  scales: {{
    x: {{ ticks: {{ color: '#8b949e', maxRotation: 45, font: {{ size: 10 }} }}, grid: {{ color: '#21262d' }} }},
    y: {{ ticks: {{ color: '#8b949e', font: {{ size: 10 }} }}, grid: {{ color: '#21262d' }} }}
  }}
}};

// Weekly anomaly
new Chart(document.getElementById('weeklyChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(weekly_dates)},
    datasets: [{{
      label: 'Niño-3.4 Anomaly (°C)',
      data: {json.dumps(weekly_anoms)},
      backgroundColor: {json.dumps(weekly_anoms)}.map(v =>
        v >= 0.5 ? '#fa8c16' : v <= -0.5 ? '#2f54eb' : '#389e0d'
      ),
      borderWidth: 0,
      borderRadius: 2,
    }}]
  }},
  options: {{
    ...chartDefaults,
    plugins: {{ ...chartDefaults.plugins, annotation: {{ annotations: {{
      el: {{ type:'line', yMin:0.5, yMax:0.5, borderColor:'#fa8c16', borderDash:[4,4], borderWidth:1 }},
      la: {{ type:'line', yMin:-0.5, yMax:-0.5, borderColor:'#2f54eb', borderDash:[4,4], borderWidth:1 }}
    }} }} }},
    scales: {{ ...chartDefaults.scales, y: {{ ...chartDefaults.scales.y, title: {{ display:true, text:'°C', color:'#8b949e' }} }} }}
  }}
}});

// ONI vs RONI
new Chart(document.getElementById('oniChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(oni_labels)},
    datasets: [
      {{
        label: 'ONI (traditional)',
        data: {json.dumps(oni_values)},
        borderColor: '#fa8c16',
        backgroundColor: 'rgba(250,140,22,0.08)',
        borderWidth: 2,
        tension: 0.3,
        pointRadius: 3,
        fill: false,
      }},
      {{
        label: 'RONI (official, 2025–)',
        data: {json.dumps(roni_values)},
        borderColor: '#4dabf7',
        backgroundColor: 'rgba(77,171,247,0.08)',
        borderWidth: 2,
        tension: 0.3,
        pointRadius: 3,
        fill: false,
      }}
    ]
  }},
  options: {{
    ...chartDefaults,
    scales: {{
      ...chartDefaults.scales,
      y: {{ ...chartDefaults.scales.y, title: {{ display:true, text:'°C anomaly', color:'#8b949e' }} }}
    }}
  }}
}});

// ENSO Strength Categories — Plotly stacked bar with in-bar model counts
(function() {{
  const el = document.getElementById('strengthDiv');
  if (!el) return;
  const traces = {strength_traces_json};
  if (!traces.length) return;
  const layout = {strength_layout_json};
  Plotly.newPlot(el, traces, layout, {{
    responsive: true, displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d','select2d','autoScale2d'],
  }});
}})();

// SST Model Forecast Plume — Plotly line chart, hover shows individual model
(function() {{
  const el = document.getElementById('plumeDiv');
  if (!el) return;
  const traces = {plume_traces_json};
  if (!traces.length) return;
  const layout = {plume_layout_json};
  Plotly.newPlot(el, traces, layout, {{
    responsive: true, displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d','select2d'],
  }});
}})();
</script>
<script>
// Info icon: flip tooltip below when near viewport top; click-to-toggle on touch
document.querySelectorAll('.info-icon').forEach(function(el) {{
  function checkFlip() {{
    var rect = el.getBoundingClientRect();
    el.classList.toggle('tip-below', rect.top < 160);
  }}
  el.addEventListener('mouseenter', checkFlip);
  el.addEventListener('click', function(e) {{
    e.stopPropagation();
    checkFlip();
    var wasActive = el.classList.contains('active');
    document.querySelectorAll('.info-icon.active').forEach(function(x) {{ x.classList.remove('active'); }});
    if (!wasActive) el.classList.add('active');
  }});
}});
document.addEventListener('click', function() {{
  document.querySelectorAll('.info-icon.active').forEach(function(x) {{ x.classList.remove('active'); }});
}});
</script>
</body>
</html>
"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard written → {output_path}")


if __name__ == "__main__":
    import sys
    data_path = sys.argv[1] if len(sys.argv) > 1 else "enso_data.json"
    # print(f"Rendering dashboard from {data_path} ...")
    with open(data_path) as f:
        data = json.load(f)
    # print(f"Fetched data: {data}")
    render(data)
