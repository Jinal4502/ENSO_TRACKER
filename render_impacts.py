"""
render_impacts.py
Generates docs/impacts.html — ENSO Global Impacts page.
Tabs-first layout: each domain is a full panel showing all charts immediately.
"""

import json
from pathlib import Path


DOMAIN_META = [
    {
        "key":   "gdp",
        "title": "Economic Growth",
        "icon":  "📈",
        "desc":  "Annual GDP growth rate (World Bank, 1961–2024). El Niño suppresses growth in tropical and commodity-exporting economies — Callahan &amp; Mankin (2023, <em>Science</em>) found effects persisting 5+ years after each event, not just the event year. Negative ONI (La Niña) can boost agricultural exporters through higher commodity output.",
    },
    {
        "key":   "food_prod",
        "title": "Agricultural Production",
        "icon":  "🌾",
        "desc":  "FAO Food Production Index year-over-year change (World Bank), plus individual crop yields (OWID/FAO). ENSO shifts precipitation regimes across major growing regions: El Niño dries out South Asia and Australia while wetting Peru and East Africa, creating winners and losers across the global food system.",
    },
    {
        "key":   "food_price",
        "title": "Food Commodity Prices",
        "icon":  "🛒",
        "desc":  "FAO Food Price Index year-over-year change, with five sub-indices (Cereals, Meat, Dairy, Oils, Sugar). El Niño–driven droughts in major growing regions can spike commodity prices with a 0–2 year lag as production shortfalls feed through to global markets. La Niña can have the opposite effect.",
    },
    {
        "key":   "disasters",
        "title": "Natural Disasters",
        "icon":  "🌪",
        "desc":  "Global natural disaster counts and economic damage year-over-year change (OWID/EM-DAT). El Niño intensifies droughts and wildfires across the Indo-Pacific while suppressing Atlantic hurricanes; La Niña amplifies flooding across South Asia, East Africa, and northern Australia. Confound-year exclusion is omitted here — ENSO causes these disasters, so the correlation is the signal, not the noise.",
    },
    {
        "key":   "fisheries",
        "title": "Peru Fisheries",
        "icon":  "🐟",
        "desc":  "Peru total marine capture YoY % change (World Bank / FAO FishStat, 1961–2024). ~80–90% is Peruvian anchoveta (<em>Engraulis ringens</em>) — the world&rsquo;s largest single-species fishery. El Niño warm-water intrusions suppress cold Humboldt upwelling, collapsing anchoveta populations: &minus;62% in 1972–73, &minus;55% in 1983, &minus;45% in 1998.",
    },
]

# Per-chart explanations (same across all domains)
CHART_DESCS = {
    "ts": (
        "Bars show the annual year-over-year % change in the selected metric. "
        "The orange line is the Oceanic Niño Index (ONI, right axis) — positive values indicate El Niño, negative La Niña. "
        "Red shading marks El Niño periods (ONI ≥ 0.5 °C), blue marks La Niña, and amber-hatched bands are major confound events "
        "(recessions, wars) that can drive large metric swings independently of ENSO."
    ),
    "lag": (
        "Pearson r (linear) and Spearman ρ (rank-based) between annual ONI and the metric at lags 0–5 years — i.e., "
        "how strongly El Niño intensity in year T predicts the metric in year T + lag. "
        "Blue bars = positive correlation; red = negative. "
        "Lighter outlined bars exclude years overlapping known confound events. "
        "The lag with the highest |r| gives the typical delay between an ENSO event and its impact."
    ),
    "table": (
        "Full correlation breakdown at every lag. "
        "'All years' uses the complete record; 'Excl. confounds' drops years where a recession or war overlaps "
        "either the ONI year or the lagged metric year. "
        "A sharp drop in |r| after exclusion suggests the full-sample correlation is partly driven by coincidental macro shocks."
    ),
    "scatter": (
        "Each point is one year, coloured by ENSO phase, plotted with ONI on the x-axis and the metric "
        "at its peak-lag offset on the y-axis. "
        "Well-separated red (El Niño) and blue (La Niña) clusters indicate a strong phase signal. "
        "The dotted regression line and Pearson r summarise the overall linear trend across the full ONI range."
    ),
    "condmeans": (
        "Mean metric value during El Niño, Neutral, and La Niña years at lag 0. "
        "Error bars show ±1 standard deviation. "
        "When the El Niño and La Niña bars are separated by more than their combined uncertainty, "
        "there is a statistically meaningful phase response. Overlapping bars suggest ENSO phase alone is a weak same-year predictor."
    ),
    "sea": (
        "Composite metric trajectory centred on El Niño (red) and La Niña (blue) event years, "
        "averaged across all events from 2 years before to 3 years after onset. Shaded bands show ±1σ. "
        "A sharp anomaly near year 0 that reverts by year +2–3 suggests a direct, time-limited ENSO impact. "
        "Persistent post-event anomalies point to lingering economic or ecological effects."
    ),
    "rolling": (
        "Rolling Pearson r between annual ONI and the metric (at lag 0) computed over a 20-year sliding window. "
        "Tracks whether the ENSO–metric relationship has strengthened or weakened over decades — "
        "for example, as global supply chains, agricultural technology, or climate itself changed. "
        "Dotted lines at r = ±0.5 mark conventional 'moderate correlation' thresholds."
    ),
}


def _panel_html(meta: dict) -> str:
    k   = meta["key"]
    cid = "dom_" + k
    is_disaster   = k == "disasters"
    is_food_prod  = k == "food_prod"
    is_food_price = k == "food_price"
    excl_th = "" if is_disaster else (
        '<th colspan="3" class="excl-col" '
        'style="border-left:1px solid var(--border);padding-left:.5rem">Excl. confounds</th>'
    )
    excl_th2 = "" if is_disaster else (
        '<th class="excl-col" style="border-left:1px solid var(--border)">n</th>'
        '<th class="excl-col">Pearson r</th><th class="excl-col">Spearman ρ</th>'
    )

    sub_controls = ""
    if is_disaster:
        sub_controls = f"""<select class="ctrl-sel {cid}_metric">
          <option value="count">Event count</option>
          <option value="damage">Econ. damage</option>
        </select>"""
    elif is_food_prod:
        sub_controls = f"""<select class="ctrl-sel {cid}_crop">
          <option value="index">Production Index</option>
          <option value="wheat">Wheat Yield</option>
          <option value="rice">Rice Yield</option>
          <option value="maize">Maize (Corn) Yield</option>
          <option value="soybean">Soybean Yield</option>
        </select>"""
    elif is_food_price:
        sub_controls = f"""<select class="ctrl-sel {cid}_cat">
          <option value="composite">Composite FPI</option>
          <option value="cereals">Cereals</option>
          <option value="meat">Meat</option>
          <option value="dairy">Dairy</option>
          <option value="oils">Oils</option>
          <option value="sugar">Sugar</option>
        </select>"""

    cd = CHART_DESCS

    return f"""
<div class="domain-panel" id="panel_{k}">
  <div class="panel-header">
    <div>
      <h2 class="panel-title">{meta["icon"]} {meta["title"]}</h2>
      <p class="panel-desc">{meta["desc"]}</p>
    </div>
    <div class="ctrl-row">
      <select class="ctrl-sel {cid}_sel"></select>
      {sub_controls}
    </div>
  </div>

  <!-- 1. Time series -->
  <div class="chart-section">
    <div class="chart-label">Time Series</div>
    <p class="chart-desc">{cd["ts"]}</p>
    <div id="{cid}_ts"></div>
  </div>

  <!-- 2. Lag correlation + table -->
  <div class="chart-grid-2">
    <div class="chart-section">
      <div class="chart-label">Lagged Cross-Correlation (ONI → Metric)</div>
      <p class="chart-desc">{cd["lag"]}</p>
      <div id="{cid}_lag"></div>
    </div>
    <div class="chart-section">
      <div class="chart-label">Correlation Table</div>
      <p class="chart-desc">{cd["table"]}</p>
      <div style="overflow-x:auto;margin-top:.25rem">
        <table class="corr-table">
          <thead><tr>
            <th>Lag</th>
            <th colspan="3" style="border-left:1px solid var(--border);padding-left:.5rem">All years</th>
            {excl_th}
          </tr><tr>
            <th></th><th>n</th><th>Pearson r</th><th>Spearman ρ</th>
            {excl_th2}
          </tr></thead>
          <tbody class="corr-tbody" id="{cid}_tbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- 3. Scatter + Conditional means -->
  <div class="chart-grid-2">
    <div class="chart-section">
      <div class="chart-label">Scatter Plot (ONI vs Metric at Peak Lag)</div>
      <p class="chart-desc">{cd["scatter"]}</p>
      <div id="{cid}_scatter"></div>
    </div>
    <div class="chart-section">
      <div class="chart-label">Conditional Means by ENSO Phase</div>
      <p class="chart-desc">{cd["condmeans"]}</p>
      <div id="{cid}_condmeans"></div>
    </div>
  </div>

  <!-- 4. SEA -->
  <div class="chart-section">
    <div class="chart-label">Superposed Epoch Analysis (SEA)</div>
    <p class="chart-desc">{cd["sea"]}</p>
    <div id="{cid}_sea"></div>
  </div>

  <!-- 5. Rolling correlation -->
  <div class="chart-section">
    <div class="chart-label">Rolling 20-Year Pearson Correlation</div>
    <p class="chart-desc">{cd["rolling"]}</p>
    <div id="{cid}_rolling"></div>
  </div>
</div>"""


def render_impacts(data: dict, output_path: str = "docs/impacts.html") -> None:
    data_js   = json.dumps(data, separators=(",", ":"))
    tab_btns  = "\n  ".join(
        f'<button class="tab-btn" data-dom="{m["key"]}" onclick="activateTab(\'{m["key"]}\')">'
        f'{m["icon"]} {m["title"]}</button>'
        for m in DOMAIN_META
    )
    panels_html = "\n".join(_panel_html(m) for m in DOMAIN_META)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ENSO Global Impacts</title>
<script src="https://cdn.plot.ly/plotly-2.30.0.min.js" charset="utf-8"></script>
<style>
  :root {{
    --bg:     #0d1117;
    --card:   #161b22;
    --border: #30363d;
    --text:   #c9d1d9;
    --muted:  #8b949e;
    --accent: hsl(265,75%,62%);
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text);
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
         padding:1.5rem; }}

  /* ── Nav ── */
  .topnav {{ display:flex; align-items:center; justify-content:space-between;
             padding:.5rem 0; border-bottom:1px solid var(--border); margin-bottom:1.2rem; }}
  .nav-brand {{ font-weight:700; font-size:.95rem; color:var(--text); text-decoration:none; }}
  .nav-links {{ display:flex; gap:.4rem; flex-wrap:wrap; }}
  .nav-links a {{ color:var(--muted); text-decoration:none; font-size:.82rem;
                  padding:.3rem .7rem; border-radius:5px; }}
  .nav-links a:hover {{ color:var(--text); background:var(--card); }}
  .nav-links a.nav-active {{ color:#fff; background:#f5a623; font-weight:600; }}

  /* ── Page header ── */
  h1 {{ font-size:1.4rem; font-weight:700; margin-bottom:.2rem; }}
  .subtitle {{ color:var(--muted); font-size:.85rem; margin-bottom:1rem; }}

  /* ── Shared legend ── */
  .legend-row {{ display:flex; gap:1.2rem; flex-wrap:wrap; margin-bottom:1rem;
                 font-size:.73rem; color:var(--muted); align-items:center; }}
  .swatch {{ display:inline-block; width:14px; height:10px; border-radius:2px; margin-right:3px; }}
  .hatch-swatch {{ display:inline-block; width:14px; height:10px; border-radius:2px;
    background:repeating-linear-gradient(45deg,#b8860033,#b8860033 2px,#b8860011 2px,#b8860011 6px);
    border:1px solid #b8860066; margin-right:3px; }}

  /* ── Domain tabs ── */
  .tab-bar {{ display:flex; gap:.3rem; flex-wrap:wrap;
              border-bottom:2px solid var(--border); margin-bottom:1.2rem; padding-bottom:0; }}
  .tab-btn {{ background:var(--card); border:1px solid var(--border); border-bottom:none;
              color:var(--muted); font-size:.8rem; padding:.45rem 1rem;
              border-radius:6px 6px 0 0; cursor:pointer; transition:all .15s;
              position:relative; top:2px; }}
  .tab-btn:hover {{ color:var(--text); background:rgba(255,255,255,.05); }}
  .tab-btn.active {{ background:var(--accent); border-color:var(--accent);
                     color:#fff; font-weight:600; }}

  /* ── Domain panels ── */
  .domain-panel {{ display:none; }}
  .domain-panel.active {{ display:block; }}

  .panel-header {{ display:flex; align-items:flex-start; justify-content:space-between;
                   gap:1rem; margin-bottom:1rem; flex-wrap:wrap; }}
  .panel-title {{ font-size:1.1rem; font-weight:700; margin-bottom:.25rem; }}
  .panel-desc {{ font-size:.78rem; color:var(--muted); line-height:1.6; max-width:680px; }}
  .ctrl-row {{ display:flex; gap:.4rem; align-items:center; flex-wrap:wrap; flex-shrink:0; }}
  .ctrl-sel {{ background:var(--bg); color:var(--text); border:1px solid var(--border);
               border-radius:4px; padding:.28rem .55rem; font-size:.78rem; cursor:pointer; }}

  /* ── Chart sections ── */
  .chart-section {{ background:var(--card); border:1px solid var(--border);
                    border-radius:8px; padding:1rem; margin-bottom:1rem; }}
  .chart-label {{ font-size:.72rem; font-weight:700; text-transform:uppercase;
                  letter-spacing:.06em; color:var(--muted);
                  padding-bottom:.35rem; margin-bottom:.3rem;
                  border-bottom:1px solid var(--border); }}
  .chart-desc {{ font-size:.75rem; color:var(--muted); line-height:1.6;
                 margin-bottom:.6rem; }}
  .chart-grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-bottom:1rem; }}
  @media(max-width:760px) {{ .chart-grid-2 {{ grid-template-columns:1fr; }} }}

  /* ── Correlation table ── */
  .corr-table {{ width:100%; font-size:.74rem; border-collapse:collapse; }}
  .corr-table th {{ color:var(--muted); text-align:left; padding:.28rem .5rem;
                    border-bottom:1px solid var(--border); font-weight:400; }}
  .corr-table td {{ padding:.28rem .5rem; border-bottom:1px solid #21262d; }}
  .corr-pos {{ color:#58a6ff; }}
  .corr-neg {{ color:#ef5350; }}
  .corr-weak {{ color:var(--muted); }}

  footer {{ font-size:.75rem; color:var(--muted); margin-top:1.5rem; text-align:center; }}
  footer a {{ color:var(--muted); }}
</style>
</head>
<body>

<nav class="topnav">
  <a class="nav-brand" href="index.html">ENSO Tracker</a>
  <div class="nav-links">
    <a href="index.html">ENSO Dashboard</a>
    <a href="hurricanes.html">Cyclones</a>
    <a href="precipitation.html">Precipitation</a>
    <a href="temperature.html">Temperature</a>
    <a href="sst.html">SST</a>
    <a href="impacts.html" class="nav-active">Impacts</a>
    <a href="facts.html">Quick Facts</a>
    <a href="research.html">Research</a>
  </div>
</nav>

<h1>ENSO Global Impacts</h1>
<p class="subtitle">How El Niño &amp; La Niña correlate with economic growth, food, commodity prices, disasters, and fisheries — 1961–2024.</p>

<div class="legend-row">
  <span><span class="swatch" style="background:rgba(239,83,80,0.3)"></span>El Niño (ONI ≥ 0.5 °C)</span>
  <span><span class="swatch" style="background:rgba(30,136,229,0.3)"></span>La Niña (ONI ≤ −0.5 °C)</span>
  <span><span class="hatch-swatch"></span>Confound event (recession / war)</span>
  <span>Bars = metric YoY % &nbsp;|&nbsp; Orange line = ONI (right axis)</span>
</div>

<div class="tab-bar">
  {tab_btns}
</div>

{panels_html}

<footer>
  Data updated: <span id="ts"></span> &nbsp;·&nbsp;
  ONI: <a href="https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt" target="_blank">NOAA/CPC</a> &nbsp;·&nbsp;
  GDP &amp; Food Production: <a href="https://data.worldbank.org" target="_blank">World Bank</a> &nbsp;·&nbsp;
  Food Prices: <a href="https://www.fao.org/worldfoodsituation/foodpricesindex/en/" target="_blank">FAO</a> &nbsp;·&nbsp;
  Disasters: <a href="https://ourworldindata.org/natural-disasters" target="_blank">OWID / EM-DAT</a>
</footer>

<script>
const D = {data_js};

// ── ENSO helpers ──────────────────────────────────────────────────────────────
function ensoPhase(oni) {{
  return oni >= 0.5 ? "el_nino" : oni <= -0.5 ? "la_nina" : "neutral";
}}

function ensoShapes(oni_annual) {{
  const years = Object.keys(oni_annual).map(Number).sort((a,b)=>a-b);
  const shapes = [];
  let runStart = null, runPhase = null;
  for (const yr of years) {{
    const ph = ensoPhase(oni_annual[yr]);
    if (ph === runPhase) continue;
    if (runPhase && runPhase !== "neutral") {{
      shapes.push({{type:"rect",layer:"below",xref:"x",yref:"paper",
        x0:runStart-0.5,x1:yr-0.5,y0:0,y1:1,
        fillcolor:runPhase==="el_nino"?"rgba(239,83,80,0.15)":"rgba(30,136,229,0.15)",
        line:{{width:0}}}});
    }}
    runStart = yr; runPhase = ph;
  }}
  if (runPhase && runPhase !== "neutral") {{
    shapes.push({{type:"rect",layer:"below",xref:"x",yref:"paper",
      x0:runStart-0.5,x1:years[years.length-1]+0.5,y0:0,y1:1,
      fillcolor:runPhase==="el_nino"?"rgba(239,83,80,0.15)":"rgba(30,136,229,0.15)",
      line:{{width:0}}}});
  }}
  return shapes;
}}

function confoundShapes(events) {{
  return events.map(ev=>({{type:"rect",layer:"below",xref:"x",yref:"paper",
    x0:ev.start-0.5,x1:ev.end+0.5,y0:0,y1:1,
    fillcolor:"rgba(184,134,0,0.12)",
    line:{{color:"rgba(184,134,0,0.35)",width:1,dash:"dot"}}}}));
}}

function confoundAnnotations(events, xRange) {{
  return events
    .filter(ev => ev.end >= xRange[0] && ev.start <= xRange[1])
    .map(ev=>({{xref:"x",yref:"paper",x:(ev.start+ev.end)/2,y:0.98,
      text:ev.name,textangle:-90,showarrow:false,
      font:{{size:8.5,color:"rgba(220,170,40,0.85)"}},
      xanchor:"center",yanchor:"top"}}));
}}

// ── Layout bases ──────────────────────────────────────────────────────────────
const BG="#0d1117",CARD="#161b22",TEXT="#c9d1d9",MUTED="#8b949e",GRID="#21262d";

function baseLayout(title, yLabel, xRange, shapes, annotations) {{
  return {{
    paper_bgcolor:CARD,plot_bgcolor:CARD,
    margin:{{t:36,r:64,b:40,l:58}},height:230,
    font:{{color:TEXT,size:11}},
    title:{{text:title,font:{{size:12,color:TEXT}},x:0,xanchor:"left",pad:{{l:2}}}},
    xaxis:{{range:xRange,gridcolor:GRID,zeroline:false,tickfont:{{size:10,color:MUTED}}}},
    yaxis:{{title:{{text:yLabel,font:{{size:10,color:MUTED}}}},gridcolor:GRID,
            zeroline:true,zerolinecolor:"#444",tickfont:{{size:10,color:MUTED}}}},
    yaxis2:{{title:{{text:"ONI (°C)",font:{{size:10,color:MUTED}}}},
             overlaying:"y",side:"right",zeroline:false,showgrid:false,
             tickfont:{{size:10,color:MUTED}}}},
    shapes,annotations:annotations||[],
    showlegend:true,
    legend:{{bgcolor:"rgba(0,0,0,0)",font:{{size:10,color:MUTED}},x:0,y:1.05,orientation:"h"}},
  }};
}}

function lagLayout(title) {{
  return {{
    paper_bgcolor:CARD,plot_bgcolor:CARD,
    margin:{{t:28,r:10,b:42,l:58}},height:175,
    font:{{color:TEXT,size:10}},
    title:{{text:title,font:{{size:10,color:MUTED}},x:0,xanchor:"left"}},
    xaxis:{{title:{{text:"Lag (years)",font:{{size:9,color:MUTED}}}},
            gridcolor:GRID,tickfont:{{size:9,color:MUTED}},zeroline:false,tickvals:[0,1,2,3,4,5]}},
    yaxis:{{title:{{text:"Correlation",font:{{size:9,color:MUTED}}}},
            gridcolor:GRID,zeroline:true,zerolinecolor:"#555",
            tickfont:{{size:9,color:MUTED}},range:[-1,1]}},
    barmode:"group",showlegend:true,
    legend:{{bgcolor:"rgba(0,0,0,0)",font:{{size:9,color:MUTED}},x:0,y:1.08,orientation:"h"}},
  }};
}}

// ── Colour helpers ────────────────────────────────────────────────────────────
const BAR_COLORS={{pos:"rgba(88,166,255,0.7)",neg:"rgba(239,83,80,0.7)",neutral:"rgba(139,148,158,0.5)"}};
function barColor(vals) {{
  return vals.map(v=>v==null?BAR_COLORS.neutral:(v>=0?BAR_COLORS.pos:BAR_COLORS.neg));
}}

const PHASE_COLORS={{el_nino:"rgba(239,83,80,0.75)",neutral:"rgba(139,148,158,0.55)",la_nina:"rgba(30,136,229,0.75)"}};
const PHASE_LABELS={{el_nino:"El Niño",neutral:"Neutral",la_nina:"La Niña"}};

// ── ONI trace ─────────────────────────────────────────────────────────────────
const oniYears  = Object.keys(D.oni_annual).map(Number).sort((a,b)=>a-b);
function oniTrace(xRange) {{
  const ys=oniYears.filter(y=>y>=xRange[0]&&y<=xRange[1]);
  return {{type:"scatter",mode:"lines",name:"ONI",x:ys,y:ys.map(y=>D.oni_annual[y]),
    yaxis:"y2",line:{{color:"#f5a623",width:1.5}},
    hovertemplate:"ONI %{{x}}: %{{y:.2f}}°C<extra></extra>"}};
}}

// ── Lag-correlation traces ────────────────────────────────────────────────────
function lagTraces(corrArr, showExcl=true) {{
  const lags=corrArr.map(c=>c.lag);
  function barTrace(name,vals,dash) {{
    return {{type:"bar",name,x:lags,y:vals,
      marker:{{color:barColor(vals),line:{{width:dash?1:0,color:"#fff"}}}},
      opacity:dash?0.65:1,hovertemplate:"%{{y:.3f}}<extra>lag %{{x}}y</extra>"}};
  }}
  const traces=[
    barTrace("Pearson (all years)",  corrArr.map(c=>c.full.pearson),  false),
    barTrace("Spearman (all years)", corrArr.map(c=>c.full.spearman), false),
  ];
  if (showExcl) {{
    traces.push(barTrace("Pearson (excl. confounds)",  corrArr.map(c=>c.excl.pearson),  true));
    traces.push(barTrace("Spearman (excl. confounds)", corrArr.map(c=>c.excl.spearman), true));
  }}
  return traces;
}}

// ── Statistical helpers ───────────────────────────────────────────────────────
function pearsonJS(xs,ys) {{
  const n=xs.length; if(n<3) return null;
  const mx=xs.reduce((a,b)=>a+b,0)/n, my=ys.reduce((a,b)=>a+b,0)/n;
  const num=xs.reduce((s,x,i)=>s+(x-mx)*(ys[i]-my),0);
  const den=Math.sqrt(xs.reduce((s,x)=>s+(x-mx)**2,0)*ys.reduce((s,y)=>s+(y-my)**2,0));
  return den===0?null:num/den;
}}
function arrMean(arr) {{ return arr.reduce((a,b)=>a+b,0)/arr.length; }}
function arrStd(arr) {{
  if(arr.length<2) return 0;
  const m=arrMean(arr);
  return Math.sqrt(arr.reduce((s,v)=>s+(v-m)**2,0)/arr.length);
}}
function linreg(xs,ys) {{
  const n=xs.length,mx=arrMean(xs),my=arrMean(ys);
  const slope=xs.reduce((s,x,i)=>s+(x-mx)*(ys[i]-my),0)/xs.reduce((s,x)=>s+(x-mx)**2,0);
  return {{slope,intercept:my-slope*mx}};
}}
function peakLag(corr) {{
  return corr.reduce((best,c)=>
    (c.full.pearson!=null&&Math.abs(c.full.pearson)>Math.abs(best.full.pearson||0))?c:best,
    corr[0]).lag;
}}

// ── Extended chart builders ───────────────────────────────────────────────────
function buildScatter(cid, series, oniByYear) {{
  const lag=peakLag(series.corr);
  const byYear={{}};
  series.years.forEach((y,i)=>byYear[y]=series.values[i]);
  const byPh={{el_nino:{{xs:[],ys:[],t:[]}},neutral:{{xs:[],ys:[],t:[]}},la_nina:{{xs:[],ys:[],t:[]}}}};
  Object.entries(oniByYear).forEach(([ys2,o])=>{{
    const yr=parseInt(ys2), m=byYear[yr+lag];
    if(o==null||m==null) return;
    const ph=ensoPhase(o);
    byPh[ph].xs.push(o); byPh[ph].ys.push(m);
    byPh[ph].t.push(`${{yr}}: ONI ${{o.toFixed(2)}}°C → ${{m.toFixed(1)}}%`);
  }});
  const allXs=[...byPh.el_nino.xs,...byPh.neutral.xs,...byPh.la_nina.xs];
  const allYs=[...byPh.el_nino.ys,...byPh.neutral.ys,...byPh.la_nina.ys];
  const r=pearsonJS(allXs,allYs);
  const traces=Object.entries(byPh).map(([ph,d])=>({{
    type:"scatter",mode:"markers",name:PHASE_LABELS[ph],
    x:d.xs,y:d.ys,text:d.t,
    marker:{{color:PHASE_COLORS[ph],size:6,line:{{width:0.5,color:"rgba(255,255,255,0.25)"}}}},
    hovertemplate:"%{{text}}<extra></extra>",
  }}));
  if(allXs.length>2) {{
    const reg=linreg(allXs,allYs);
    const xr=[Math.min(...allXs)-0.1,Math.max(...allXs)+0.1];
    traces.push({{type:"scatter",mode:"lines",
      name:`Regression (r=${{r!=null?r.toFixed(3):"—"}})`,
      x:xr,y:xr.map(x=>reg.slope*x+reg.intercept),
      line:{{color:"#f5a623",width:1.5,dash:"dot"}},hoverinfo:"skip"}});
  }}
  Plotly.react(cid+"_scatter",traces,{{
    paper_bgcolor:CARD,plot_bgcolor:CARD,margin:{{t:28,r:10,b:42,l:58}},height:230,
    font:{{color:TEXT,size:10}},
    title:{{text:`ONI vs metric at peak lag ${{lag}}y  (r=${{r!=null?r.toFixed(3):"—"}})`,
           font:{{size:10,color:MUTED}},x:0}},
    xaxis:{{title:{{text:"ONI (°C)",font:{{size:9,color:MUTED}}}},gridcolor:GRID,
            zeroline:true,zerolinecolor:"#444",tickfont:{{size:9,color:MUTED}}}},
    yaxis:{{title:{{text:"Metric YoY %",font:{{size:9,color:MUTED}}}},gridcolor:GRID,
            zeroline:true,zerolinecolor:"#444",tickfont:{{size:9,color:MUTED}}}},
    showlegend:true,
    legend:{{bgcolor:"rgba(0,0,0,0)",font:{{size:9,color:MUTED}},x:0,y:1.08,orientation:"h"}},
  }},{{responsive:true,displayModeBar:false}});
}}

function buildCondMeans(cid, series, oniByYear) {{
  const byYear={{}};
  series.years.forEach((y,i)=>byYear[y]=series.values[i]);
  const groups={{el_nino:[],neutral:[],la_nina:[]}};
  Object.entries(oniByYear).forEach(([ys2,o])=>{{
    const m=byYear[parseInt(ys2)];
    if(o==null||m==null) return;
    groups[ensoPhase(o)].push(m);
  }});
  const phases=["el_nino","neutral","la_nina"];
  const means=phases.map(ph=>groups[ph].length?arrMean(groups[ph]):null);
  const stds =phases.map(ph=>arrStd(groups[ph]));
  const ns   =phases.map(ph=>groups[ph].length);
  Plotly.react(cid+"_condmeans",[{{
    type:"bar",x:phases.map(ph=>PHASE_LABELS[ph]),y:means,
    error_y:{{type:"data",array:stds,visible:true,color:"#8b949e",thickness:1.5,width:4}},
    marker:{{color:phases.map(ph=>PHASE_COLORS[ph])}},customdata:ns,
    hovertemplate:"%{{x}}: %{{y:.2f}}% ± %{{error_y.array:.2f}}<br>n=%{{customdata}}<extra></extra>",
  }}],{{
    paper_bgcolor:CARD,plot_bgcolor:CARD,margin:{{t:28,r:10,b:42,l:58}},height:220,
    font:{{color:TEXT,size:10}},
    title:{{text:"Mean metric value by ENSO phase (lag 0)",font:{{size:10,color:MUTED}},x:0}},
    xaxis:{{gridcolor:GRID,tickfont:{{size:9,color:MUTED}}}},
    yaxis:{{title:{{text:"Mean YoY %",font:{{size:9,color:MUTED}}}},gridcolor:GRID,
            zeroline:true,zerolinecolor:"#555",tickfont:{{size:9,color:MUTED}}}},
    showlegend:false,
  }},{{responsive:true,displayModeBar:false}});
}}

function buildSEA(cid, series, oniByYear) {{
  const byYear={{}};
  series.years.forEach((y,i)=>byYear[y]=series.values[i]);
  const LAGS=[-2,-1,0,1,2,3];
  const enYrs=Object.entries(oniByYear).filter(([,v])=>v>=0.5).map(([y])=>parseInt(y));
  const lnYrs=Object.entries(oniByYear).filter(([,v])=>v<=-0.5).map(([y])=>parseInt(y));
  function comp(evtYears) {{
    return LAGS.map(lag=>{{
      const vals=evtYears.map(t=>byYear[t+lag]).filter(v=>v!=null);
      if(!vals.length) return {{mean:null,std:0,n:0}};
      return {{mean:arrMean(vals),std:arrStd(vals),n:vals.length}};
    }});
  }}
  function seaTraces(compData,name,lineColor,fillColor) {{
    const means=compData.map(c=>c.mean),stds=compData.map(c=>c.std);
    const upper=means.map((m,i)=>m!=null?m+stds[i]:null);
    const lower=means.map((m,i)=>m!=null?m-stds[i]:null);
    const lagsRev=[...LAGS].reverse();
    return [
      {{type:"scatter",mode:"lines+markers",name,x:LAGS,y:means,
        line:{{color:lineColor,width:2}},marker:{{color:lineColor,size:5}},
        hovertemplate:`${{name}} lag %{{x}}y: %{{y:.2f}}%<extra></extra>`}},
      {{type:"scatter",mode:"lines",name:`${{name}} ±1σ`,showlegend:false,
        x:[...LAGS,...lagsRev],
        y:[...upper,...lagsRev.map((_,i)=>lower[LAGS.length-1-i])],
        fill:"toself",fillcolor:fillColor,line:{{width:0}},hoverinfo:"skip"}},
    ];
  }}
  Plotly.react(cid+"_sea",[
    ...seaTraces(comp(enYrs),"El Niño","rgba(239,83,80,0.85)","rgba(239,83,80,0.1)"),
    ...seaTraces(comp(lnYrs),"La Niña","rgba(30,136,229,0.85)","rgba(30,136,229,0.1)"),
  ],{{
    paper_bgcolor:CARD,plot_bgcolor:CARD,margin:{{t:28,r:10,b:42,l:58}},height:240,
    font:{{color:TEXT,size:10}},
    title:{{text:"Composite metric trajectory centred on ENSO event years (mean ±1σ)",
           font:{{size:10,color:MUTED}},x:0}},
    xaxis:{{title:{{text:"Years relative to ENSO event onset",font:{{size:9,color:MUTED}}}},
            gridcolor:GRID,zeroline:true,zerolinecolor:"#555",
            tickvals:LAGS,tickfont:{{size:9,color:MUTED}}}},
    yaxis:{{title:{{text:"Composite YoY %",font:{{size:9,color:MUTED}}}},
            gridcolor:GRID,zeroline:true,zerolinecolor:"#555",tickfont:{{size:9,color:MUTED}}}},
    shapes:[{{type:"line",xref:"x",yref:"paper",x0:-0.5,x1:-0.5,y0:0,y1:1,
              line:{{color:"#555",dash:"dot",width:1}}}}],
    showlegend:true,
    legend:{{bgcolor:"rgba(0,0,0,0)",font:{{size:9,color:MUTED}},x:0,y:1.08,orientation:"h"}},
  }},{{responsive:true,displayModeBar:false}});
}}

function buildRollingCorr(cid, series, oniByYear, winSize=20) {{
  const byYear={{}};
  series.years.forEach((y,i)=>byYear[y]=series.values[i]);
  const allYrs=Object.keys(oniByYear).map(Number).sort((a,b)=>a-b);
  const pts=[];
  for(let i=winSize-1;i<allYrs.length;i++) {{
    const win=allYrs.slice(i-winSize+1,i+1);
    const xs=[],ys=[];
    win.forEach(y=>{{const o=oniByYear[y],m=byYear[y];if(o!=null&&m!=null){{xs.push(o);ys.push(m);}}}});
    if(xs.length>=Math.floor(winSize*0.7)) {{
      const r=pearsonJS(xs,ys);
      if(r!=null) pts.push({{year:allYrs[i-Math.floor(winSize/2)],r}});
    }}
  }}
  Plotly.react(cid+"_rolling",[
    {{type:"scatter",mode:"lines",name:"20-yr rolling Pearson r",
      x:pts.map(d=>d.year),y:pts.map(d=>d.r),
      line:{{color:"#9e78c6",width:2}},
      hovertemplate:"%{{x}}: r=%{{y:.3f}}<extra></extra>"}},
  ],{{
    paper_bgcolor:CARD,plot_bgcolor:CARD,margin:{{t:28,r:10,b:42,l:58}},height:190,
    font:{{color:TEXT,size:10}},
    title:{{text:"Rolling 20-year Pearson r (ONI vs metric, lag 0)",font:{{size:10,color:MUTED}},x:0}},
    xaxis:{{gridcolor:GRID,zeroline:false,tickfont:{{size:9,color:MUTED}}}},
    yaxis:{{title:{{text:"r",font:{{size:9,color:MUTED}}}},range:[-1,1],
            gridcolor:GRID,zeroline:true,zerolinecolor:"#555",tickfont:{{size:9,color:MUTED}}}},
    shapes:[
      {{type:"line",xref:"paper",yref:"y",x0:0,x1:1,y0: 0.5,y1: 0.5,line:{{color:"#555",dash:"dot",width:1}}}},
      {{type:"line",xref:"paper",yref:"y",x0:0,x1:1,y0:-0.5,y1:-0.5,line:{{color:"#555",dash:"dot",width:1}}}},
    ],
    showlegend:false,
  }},{{responsive:true,displayModeBar:false}});
}}

// ── Domain builder ────────────────────────────────────────────────────────────
function resolveSeries(entry, metric) {{
  if (!entry) return null;
  if (metric === "damage" && entry.damage) return entry.damage;
  if (entry.count) return entry.count;
  return entry;
}}

function buildDomain(domKey) {{
  const dom = D.domains[domKey];
  if (!dom || !dom.countries) return;
  const countries = dom.countries;
  const keyList   = Object.keys(countries);
  if (!keyList.length) return;

  const isDisaster   = !!countries[keyList[0]].count;
  const cid          = "dom_" + domKey;
  const container    = document.getElementById("panel_" + domKey);

  const sel = container.querySelector("." + cid + "_sel");
  keyList.forEach(k => {{
    const opt = document.createElement("option");
    opt.value = k; opt.textContent = countries[k].name || k;
    sel.appendChild(opt);
  }});

  let currentMetric = "count";
  const metricSel = container.querySelector("." + cid + "_metric");
  if (metricSel) metricSel.addEventListener("change", () => {{ currentMetric = metricSel.value; plot(sel.value); }});

  let currentSub = domKey === "food_prod" ? "index" : domKey === "food_price" ? "composite" : null;
  const cropSel = container.querySelector("." + cid + "_crop");
  const catSel  = container.querySelector("." + cid + "_cat");
  if (cropSel) cropSel.addEventListener("change", () => {{ currentSub = cropSel.value; plot(sel.value); }});
  if (catSel)  catSel.addEventListener("change",  () => {{ currentSub = catSel.value;  plot(sel.value); }});

  const CROP_LABELS = {{wheat:"Wheat Yield",rice:"Rice Yield",maize:"Maize Yield",soybean:"Soybean Yield"}};
  const CAT_LABELS  = {{cereals:"Cereals",meat:"Meat",dairy:"Dairy",oils:"Oils",sugar:"Sugar"}};

  function getActiveSeries(entry) {{
    if (domKey === "food_prod" && currentSub && currentSub !== "index")
      return (entry.crops && entry.crops[currentSub]) || null;
    if (domKey === "food_price" && currentSub && currentSub !== "composite")
      return (entry.sub_indices && entry.sub_indices[currentSub]) || null;
    return resolveSeries(entry, currentMetric);
  }}

  function plot(key) {{
    const entry  = countries[key];
    const series = getActiveSeries(entry);
    if (!series || !series.years || !series.years.length) return;

    const yrs    = series.years, vals = series.values;
    const xRange = [Math.min(...yrs)-1, Math.max(...yrs)+1];
    const allShapes = [...confoundShapes(D.confound_events), ...ensoShapes(D.oni_annual)];

    let seriesLabel, chartTitle;
    if (domKey === "food_prod" && currentSub && currentSub !== "index") {{
      seriesLabel = (CROP_LABELS[currentSub]||currentSub) + " YoY %";
      chartTitle  = seriesLabel + " — " + (entry.name||key);
    }} else if (domKey === "food_price" && currentSub && currentSub !== "composite") {{
      seriesLabel = "FAO " + (CAT_LABELS[currentSub]||currentSub) + " Price YoY %";
      chartTitle  = seriesLabel + " — " + (entry.name||key);
    }} else if (isDisaster) {{
      seriesLabel = currentMetric === "damage" ? "Econ. damage YoY %" : "Event count YoY %";
      chartTitle  = dom.label + " — " + (entry.name||key);
    }} else {{
      seriesLabel = dom.label.split("(")[0].trim();
      chartTitle  = dom.label + " — " + (entry.name||key);
    }}

    const rawMt = (domKey === "fisheries" && entry.raw_mt) ? entry.raw_mt : null;
    const customdata = rawMt ? yrs.map(y => rawMt[y]!=null?rawMt[y]:null) : null;
    const hoverTpl   = rawMt
      ? "%{{x}}: %{{y:.2f}}%<br>Catch: %{{customdata:.2f}} Mt<extra></extra>"
      : "%{{x}}: %{{y:.2f}}%<extra></extra>";

    const barTrace = {{
      type:"bar", name:seriesLabel, x:yrs, y:vals,
      marker:{{color:barColor(vals)}}, customdata,
      hovertemplate:hoverTpl,
    }};

    Plotly.react(cid+"_ts",
      [barTrace, oniTrace(xRange)],
      baseLayout(chartTitle, seriesLabel, xRange, allShapes, confoundAnnotations(D.confound_events, xRange)),
      {{responsive:true, displayModeBar:false}});

    Plotly.react(cid+"_lag",
      lagTraces(series.corr, !isDisaster),
      lagLayout("Pearson r / Spearman ρ — ONI → " + (entry.name||key)),
      {{responsive:true, displayModeBar:false}});

    // Correlation table
    const tbody = document.getElementById(cid+"_tbody");
    tbody.innerHTML = "";
    series.corr.forEach(row => {{
      const tr = document.createElement("tr");
      function fmt(v) {{
        if (v==null) return '<td class="corr-weak">—</td>';
        const cls = Math.abs(v)<0.1?"corr-weak":(v>=0?"corr-pos":"corr-neg");
        return `<td class="${{cls}}">${{v.toFixed(3)}}</td>`;
      }}
      const exclCells = isDisaster ? "" :
        `<td class="excl-col">${{row.excl.n}}</td>${{fmt(row.excl.pearson)}}${{fmt(row.excl.spearman)}}`;
      tr.innerHTML = `<td>${{row.lag}}y</td>
        <td>${{row.full.n}}</td>${{fmt(row.full.pearson)}}${{fmt(row.full.spearman)}}${{exclCells}}`;
      // Hide excl columns for disasters
      if (isDisaster) tr.querySelectorAll(".excl-col").forEach(el=>el.style.display="none");
      tbody.appendChild(tr);
    }});
    if (isDisaster) {{
      container.querySelectorAll(".excl-col").forEach(el=>el.style.display="none");
    }}

    buildScatter(cid, series, D.oni_annual);
    buildCondMeans(cid, series, D.oni_annual);
    buildSEA(cid, series, D.oni_annual);
    buildRollingCorr(cid, series, D.oni_annual);
  }}

  sel.addEventListener("change", () => plot(sel.value));
  plot(keyList[0]);
}}

// ── Tab switching ─────────────────────────────────────────────────────────────
const rendered = {{}};

function activateTab(domKey) {{
  document.querySelectorAll(".tab-btn").forEach(b =>
    b.classList.toggle("active", b.dataset.dom === domKey));
  document.querySelectorAll(".domain-panel").forEach(p =>
    p.classList.toggle("active", p.id === "panel_" + domKey));

  if (!rendered[domKey]) {{
    buildDomain(domKey);
    rendered[domKey] = true;
  }} else {{
    // Trigger Plotly resize in case panel was hidden during initial render
    document.querySelectorAll("#panel_" + domKey + " .js-plotly-plot")
      .forEach(el => Plotly.Plots.resize(el));
  }}
}}

// Boot: activate first tab
activateTab("gdp");

document.getElementById("ts").textContent = new Date(D.generated).toLocaleDateString();
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"Rendered → {output_path}")


def main() -> None:
    data_path = Path("docs/data/impacts_data.json")
    if not data_path.exists():
        raise FileNotFoundError(
            f"{data_path} not found — run fetch_impacts.py first"
        )
    with open(data_path) as f:
        data = json.load(f)
    render_impacts(data)


if __name__ == "__main__":
    main()
