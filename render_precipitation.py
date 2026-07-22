"""
render_precipitation.py
Generates docs/precipitation.html — Global Precipitation dashboard.
All CSV data is loaded at browser runtime by region; no server-side processing.
"""

import json
from pathlib import Path


# ── Region config ─────────────────────────────────────────────────────────────
# Embedded in the page as a JS constant so the browser knows where to fetch
# each region's CSV and how to render the map for it.
REGION_CONFIG = {
    "usa": {
        "name": "United States",
        "csv": "data/usa_monthly_grid.csv",
        "center_lat": 39.5, "center_lon": -96.0, "zoom": 2.5,
        "marker_size": 20,
        "all_label": "All USA",
        "subregion_label": "State",
        "source_html": (
            "NClimGrid monthly · 1.0° Gaussian-smoothed grid · "
            "<a href='https://www.ncei.noaa.gov/products/land-based-station/nclimgrid-monthly'"
            " target='_blank'>NOAA/NCEI</a>"
        ),
    },
    "india": {
        "name": "India",
        "csv": "data/india_monthly_grid.csv",
        "center_lat": 22.0, "center_lon": 82.0, "zoom": 3.6,
        "marker_size": 22,
        "all_label": "All India",
        "subregion_label": "Region",
        "source_html": (
            "GPCC Full Data Monthly · 1.0° grid · "
            "<a href='https://psl.noaa.gov/data/gridded/data.gpcc.html'"
            " target='_blank'>NOAA/PSL GPCC</a>"
        ),
    },
    "australia": {
        "name": "Australia",
        "csv": "data/australia_monthly_grid.csv",
        "center_lat": -26.0, "center_lon": 133.0, "zoom": 2.8,
        "marker_size": 24,
        "all_label": "All Australia",
        "subregion_label": "Region",
        "source_html": (
            "GPCC Full Data Monthly · 1.0° grid · "
            "<a href='https://psl.noaa.gov/data/gridded/data.gpcc.html'"
            " target='_blank'>NOAA/PSL GPCC</a>"
        ),
    },
    "brazil": {
        "name": "Brazil",
        "csv": "data/brazil_monthly_grid.csv",
        "center_lat": -10.0, "center_lon": -53.0, "zoom": 2.8,
        "marker_size": 24,
        "all_label": "All Brazil",
        "subregion_label": "Region",
        "source_html": (
            "GPCC Full Data Monthly · 1.0° grid · "
            "<a href='https://psl.noaa.gov/data/gridded/data.gpcc.html'"
            " target='_blank'>NOAA/PSL GPCC</a>"
        ),
    },
    "east_africa": {
        "name": "East Africa",
        "csv": "data/east_africa_monthly_grid.csv",
        "center_lat": 3.0, "center_lon": 38.0, "zoom": 3.2,
        "marker_size": 22,
        "all_label": "All East Africa",
        "subregion_label": "Region",
        "source_html": (
            "GPCC Full Data Monthly · 1.0° grid · "
            "<a href='https://psl.noaa.gov/data/gridded/data.gpcc.html'"
            " target='_blank'>NOAA/PSL GPCC</a>"
        ),
    },
}

_RC_JSON = json.dumps(REGION_CONFIG)


def render_precipitation(meta: dict, output_path: str = "docs/precipitation.html") -> None:

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Global Precipitation Tracker</title>
<script src="https://cdn.plot.ly/plotly-2.30.0.min.js" charset="utf-8"></script>
<style>
  :root {{
    --bg:     #0d1117;
    --card:   #161b22;
    --border: #30363d;
    --text:   #c9d1d9;
    --muted:  #8b949e;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text);
          font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
          padding:1.5rem; }}
  h1  {{ font-size:1.4rem; font-weight:700; margin-bottom:.2rem; }}
  h2  {{ font-size:.78rem; text-transform:uppercase; letter-spacing:.05em;
         color:var(--muted); margin-bottom:.6rem; }}
  .subtitle {{ color:var(--muted); font-size:.85rem; margin-bottom:1.5rem; }}
  .subtitle a {{ color:#58a6ff; text-decoration:none; }}
  .card {{ background:var(--card); border:1px solid var(--border);
           border-radius:8px; padding:1rem; margin-bottom:1.5rem; }}
  #content {{ display:none; }}
  .topnav {{ display:flex; align-items:center; justify-content:space-between;
             padding:.5rem 0; border-bottom:1px solid var(--border); margin-bottom:1.2rem; }}
  .nav-brand {{ font-weight:700; font-size:.95rem; color:var(--text); text-decoration:none; }}
  .nav-links {{ display:flex; gap:.4rem; }}
  .nav-links a {{ color:var(--muted); text-decoration:none; font-size:.82rem;
                 padding:.3rem .7rem; border-radius:5px; }}
  .nav-links a:hover {{ color:var(--text); background:var(--card); }}
  .nav-links a.nav-active {{ color:#fff; background:#f5a623; font-weight:600; }}
  .btn-row {{ display:flex; gap:.4rem; flex-wrap:wrap; margin-bottom:.8rem; }}
  .btn {{ background:var(--card); border:1px solid var(--border); color:var(--muted);
          padding:.3rem .8rem; border-radius:16px; font-size:.78rem; cursor:pointer;
          transition:border-color .15s, color .15s; }}
  .btn:hover {{ color:var(--text); border-color:#8b949e; }}
  .btn.active {{ background:#1f6feb; border-color:#388bfd; color:#fff; font-weight:600; }}
  .tab-row {{ display:flex; gap:0; margin-bottom:.8rem;
              border:1px solid var(--border); border-radius:6px; overflow:hidden;
              width:fit-content; }}
  .tab {{ background:transparent; border:none; color:var(--muted);
          padding:.35rem 1rem; font-size:.8rem; cursor:pointer; }}
  .tab:hover {{ color:var(--text); background:rgba(255,255,255,.04); }}
  .tab.active {{ background:#1f6feb; color:#fff; font-weight:600; }}
  footer {{ font-size:.75rem; color:var(--muted); margin-top:1.5rem; text-align:center; }}
  footer a {{ color:var(--muted); }}
  .region-bar {{ display:flex; align-items:center; gap:.8rem; flex-wrap:wrap; }}
  .region-label {{ font-size:.78rem; color:var(--muted); font-weight:600; white-space:nowrap; }}
</style>
</head>
<body>

<nav class="topnav">
  <a class="nav-brand" href="index.html">ENSO Tracker</a>
  <div class="nav-links">
    <a href="index.html">ENSO Dashboard</a>
    <a href="hurricanes.html">Cyclone Tracker</a>
    <a href="precipitation.html" class="nav-active">Precipitation</a>
  </div>
</nav>

<h1 id="pageTitle">Precipitation</h1>
<p id="pageSubtitle" class="subtitle">Loading&hellip;</p>

<div id="loading" style="text-align:center;padding:3rem;color:var(--muted)">
  Loading precipitation data&hellip;
</div>

<div id="content">

  <!-- Region selector -->
  <div class="card" style="padding:.75rem 1rem;margin-bottom:1rem">
    <div class="region-bar">
      <span class="region-label">Region:</span>
      <div class="btn-row" id="regionSelector" style="margin:0">
        <button class="btn active" data-region="usa">United States</button>
        <button class="btn" data-region="india">India</button>
        <button class="btn" data-region="australia">Australia</button>
        <button class="btn" data-region="brazil">Brazil</button>
        <button class="btn" data-region="east_africa">East Africa</button>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>Precipitation Map</h2>

    <div class="tab-row" id="mapTabs">
      <button class="tab active" data-tab="tracker">Monthly Tracker</button>
      <button class="tab"        data-tab="composite">ENSO Composite</button>
    </div>

    <div id="trackerDesc">
      <p style="font-size:.78rem;color:var(--muted);margin-bottom:.5rem">
        Use &nbsp;&#9654;&nbsp; Play or drag the year slider to step through every month.
        ENSO phase shown on the map.
      </p>
    </div>

    <div id="compositeControls" style="display:none">
      <p style="font-size:.78rem;color:var(--muted);margin-bottom:.5rem">
        Average precipitation per cell for each ENSO phase. Toggle to compare spatial patterns.
      </p>
      <div class="btn-row" id="ensoToggle">
        <button class="btn active" data-enso="all">All Years</button>
        <button class="btn" data-enso="El Ni&ntilde;o">El Ni&ntilde;o</button>
        <button class="btn" data-enso="La Ni&ntilde;a">La Ni&ntilde;a</button>
        <button class="btn" data-enso="Neutral">Neutral</button>
      </div>
    </div>

    <div id="mapDiv" style="height:540px;width:100%"></div>
  </div>

  <div class="card">
    <h2 id="subregionHeader">Select Sub-region</h2>
    <p style="font-size:.78rem;color:var(--muted);margin-bottom:.6rem">
      Click to filter the time series and climatology charts below.
    </p>
    <div class="btn-row" id="stateSelector"></div>
  </div>

  <div class="card">
    <h2 id="lineTitle">Monthly Precipitation</h2>
    <p style="font-size:.78rem;color:var(--muted);margin-bottom:.5rem">
      Area-average monthly precipitation.
      <span style="background:rgba(239,83,80,.22);padding:1px 5px;border-radius:3px">El Ni&ntilde;o</span>
      and
      <span style="background:rgba(30,136,229,.22);padding:1px 5px;border-radius:3px">La Ni&ntilde;a</span>
      periods shaded per NOAA 5-season rule.
    </p>
    <div id="lineDiv"></div>
  </div>

  <div class="card">
    <h2 id="climTitle">Monthly Climatology by ENSO Phase</h2>
    <p style="font-size:.78rem;color:var(--muted);margin-bottom:.5rem">
      Long-term average for each calendar month, split by ENSO phase.
    </p>
    <div id="climDiv"></div>
  </div>

</div>

<footer>
  ENSO: <a href="https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
           target="_blank">NOAA/CPC ONI</a>
  &nbsp;&middot;&nbsp;
  <a href="hurricanes.html">&#127744; Cyclone Tracker &rarr;</a>
</footer>

<script>
const REGION_CONFIG = {_RC_JSON};

const MONTH_NAMES  = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
let YR0 = "1970", YR1 = "2026";
const DARK = {{
  paper:"#0d1117", plot:"#0d1117", text:"#c9d1d9",
  muted:"#8b949e", grid:"#21262d", card:"#1c2128", border:"#30363d"
}};
const PRCP_SCALE = [
  [0.00,"#f0f9ff"],   // near-white  — dry
  [0.08,"#bae6fd"],   // pale sky
  [0.20,"#7dd3fc"],   // light blue
  [0.36,"#22d3ee"],   // neon cyan   — noticeable rain
  [0.54,"#06b6d4"],   // vivid teal
  [0.70,"#0284c7"],   // strong blue
  [0.85,"#0369a1"],   // deep blue
  [1.00,"#0c4a6e"],   // ocean deep  — very wet
];
const ENSO_PHASES = ["El Niño","Neutral","La Niña"];
const ENSO_COLORS = ["#ef5350","#8b949e","#1e88e5"];
const ENSO_FILL   = {{"El Niño":"rgba(239,83,80,0.18)","La Niña":"rgba(30,136,229,0.18)"}};

// ── Mutable state (reset on every region load) ────────────────────────────────
let currentRegion  = "usa";
let currentMode    = "tracker";
let csvCache       = {{}};         // regionKey → raw CSV text
let fixedLats      = [];
let fixedLons      = [];
let cellList       = [];
let monthlyData    = {{}};
let sortedKeys     = [];
let composites     = {{}};
let stateRows      = {{}};
let cmapMax        = 100;
let cachedSliderSteps = [];

// ── CSV parser ────────────────────────────────────────────────────────────────
function parseCSV(text) {{
  const lines = text.trim().split(/\\r?\\n/);
  const keys  = lines[0].split(",").map(k => k.trim());
  return lines.slice(1).filter(l => l.trim()).map(l => {{
    const v = l.split(",");
    return Object.fromEntries(keys.map((k,i) => [k,(v[i]||"").trim()]));
  }});
}}

// ── Map annotation helpers ────────────────────────────────────────────────────
function trackerAnnotations(fd) {{
  const label = MONTH_NAMES[fd.month-1]+" "+fd.year;
  const ecol  = ENSO_COLORS[ENSO_PHASES.indexOf(fd.enso)] || DARK.muted;
  return [
    {{text:label, x:0.01,y:0.97,xref:"paper",yref:"paper",
      xanchor:"left",yanchor:"top",showarrow:false,
      font:{{size:22,color:"#e6edf3",family:"monospace",weight:700}},
      bgcolor:"rgba(13,17,23,0.7)",borderpad:4}},
    {{text:fd.enso, x:0.01,y:0.86,xref:"paper",yref:"paper",
      xanchor:"left",yanchor:"top",showarrow:false,
      font:{{size:13,color:ecol,family:"monospace"}},
      bgcolor:"rgba(13,17,23,0.6)",borderpad:3}},
  ];
}}

function compositeAnnotation(phase) {{
  const label = phase==="all" ? "All Years" : phase;
  return [{{text:label, x:0.01,y:0.97,xref:"paper",yref:"paper",
    xanchor:"left",yanchor:"top",showarrow:false,
    font:{{size:16,color:"#e6edf3",family:"monospace",weight:700}},
    bgcolor:"rgba(13,17,23,0.75)",borderpad:4}}];
}}

// ── Shared map trace builder ──────────────────────────────────────────────────
function makeTrace(vals) {{
  const ms = REGION_CONFIG[currentRegion].marker_size;
  return {{
    type:"scattermapbox", mode:"markers",
    lat:fixedLats, lon:fixedLons,
    marker:{{
      size:ms, opacity:0.88,
      color:vals, colorscale:PRCP_SCALE, cmin:0, cmax:cmapMax,
      colorbar:{{
        title:{{text:"mm/mo",font:{{color:"#7dd3fc",size:10}}}},
        tickfont:{{color:"#bae6fd",size:10}},
        bgcolor:"rgba(12,17,23,0.80)",bordercolor:"#164e63",borderwidth:1,
        len:0.55,thickness:14,x:1.01,xpad:8
      }}
    }},
    hovertemplate:"<b>%{{lat:.1f}}°, %{{lon:.1f}}°</b><br>%{{marker.color:.1f}} mm/mo<extra></extra>",
    showlegend:false
  }};
}}

// ── Base mapbox layout (region-aware) ─────────────────────────────────────────
function makeBaseLayout(regionKey) {{
  const rc = REGION_CONFIG[regionKey];
  return {{
    autosize:true,
    paper_bgcolor:DARK.paper,
    uirevision:"map-"+regionKey,
    mapbox:{{style:"carto-darkmatter",center:{{lat:rc.center_lat,lon:rc.center_lon}},zoom:rc.zoom}},
  }};
}}

// ── Tracker layout (Plotly slider + play/pause) ───────────────────────────────
function makeTrackerLayout(fd, sliderSteps) {{
  return {{
    ...makeBaseLayout(currentRegion),
    margin:{{l:0,r:65,t:0,b:130}},
    annotations: trackerAnnotations(fd),
    updatemenus:[{{
      type:"buttons", showactive:false,
      x:0.01, y:0.08, xanchor:"left", yanchor:"top",
      buttons:[
        {{label:"▶  Play",  method:"animate",
          args:[null,{{frame:{{duration:250,redraw:true}},fromcurrent:true,
                       mode:"immediate",transition:{{duration:80}}}}]}},
        {{label:"⏸  Pause",method:"animate",
          args:[[null],{{frame:{{duration:0,redraw:false}},
                         mode:"immediate",transition:{{duration:0}}}}]}},
      ],
      bgcolor:"#1c2128",bordercolor:"#30363d",
      font:{{color:DARK.text,size:12}},
    }}],
    sliders:[{{
      active:0, steps:sliderSteps,
      x:0, y:0, xanchor:"left", yanchor:"top", len:1.0,
      currentvalue:{{visible:false}},
      transition:{{duration:80}},
      bgcolor:"#21262d", bordercolor:"#30363d",
      tickcolor:"#8b949e", font:{{color:DARK.muted,size:9}},
      pad:{{b:10,t:70}}, minorticklen:0,
    }}],
  }};
}}

// ── Composite layout (no animation) ──────────────────────────────────────────
function makeCompositeLayout(phase) {{
  return {{
    ...makeBaseLayout(currentRegion),
    margin:{{l:0,r:65,t:0,b:20}},
    annotations:compositeAnnotation(phase),
    updatemenus:[], sliders:[],
  }};
}}

// ── Tab switching ─────────────────────────────────────────────────────────────
document.getElementById("mapTabs").addEventListener("click", e => {{
  const btn = e.target.closest("[data-tab]");
  if (!btn || btn.dataset.tab === currentMode) return;
  document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  currentMode = btn.dataset.tab;

  if (currentMode === "tracker") {{
    document.getElementById("trackerDesc").style.display = "";
    document.getElementById("compositeControls").style.display = "none";
    const fd = monthlyData[sortedKeys[0]];
    Plotly.react("mapDiv",[makeTrace(fd.vals)],
      makeTrackerLayout(fd, cachedSliderSteps),{{responsive:true}});
  }} else {{
    document.getElementById("trackerDesc").style.display = "none";
    document.getElementById("compositeControls").style.display = "";
    const activeBtn = document.querySelector("#ensoToggle .btn.active");
    const phase = activeBtn ? activeBtn.dataset.enso : "all";
    Plotly.react("mapDiv",[makeTrace(composites[phase])],
      makeCompositeLayout(phase),{{responsive:true}});
  }}
}});

// ── ENSO composite toggle ─────────────────────────────────────────────────────
document.getElementById("ensoToggle").addEventListener("click", e => {{
  const btn = e.target.closest("[data-enso]");
  if (!btn) return;
  document.querySelectorAll("#ensoToggle .btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  const phase = btn.dataset.enso;
  Plotly.react("mapDiv",[makeTrace(composites[phase])],
    makeCompositeLayout(phase),{{responsive:true}});
}});

// ── Sub-region selector (dynamically populated) ───────────────────────────────
document.getElementById("stateSelector").addEventListener("click", e => {{
  const btn = e.target.closest("[data-state]");
  if (!btn) return;
  document.querySelectorAll("#stateSelector .btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  renderTimeSeries(btn.dataset.state);
  renderClimatology(btn.dataset.state);
}});

// ── Region selector ───────────────────────────────────────────────────────────
document.getElementById("regionSelector").addEventListener("click", e => {{
  const btn = e.target.closest("[data-region]");
  if (!btn || btn.dataset.region === currentRegion) return;
  document.querySelectorAll("#regionSelector .btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  loadRegion(btn.dataset.region);
}});

// ── Time series ───────────────────────────────────────────────────────────────
function renderTimeSeries(stateKey) {{
  const rows = stateRows[stateKey]||[];
  const mdata={{}};
  for(const r of rows){{
    const k=r.year+"-"+r.month.padStart(2,"0");
    if(!mdata[k]) mdata[k]={{sum:0,cnt:0,enso:r.enso,year:+r.year,month:+r.month}};
    mdata[k].sum+=+r.prcp_mm; mdata[k].cnt++;
  }}
  const keys  = Object.keys(mdata).sort();
  const msX   = keys.map(k=>{{const d=mdata[k];return d.year+"-"+String(d.month).padStart(2,"0")+"-01";}});
  const msY   = keys.map(k=>+(mdata[k].sum/mdata[k].cnt).toFixed(2));
  const msENSO= keys.map(k=>mdata[k].enso);

  // Percentile reference lines
  const sorted=[...msY].sort((a,b)=>a-b);
  function pct(arr,p){{const i=Math.max(0,Math.round(p/100*(arr.length-1)));return arr[i];}}
  const PCT_LINES=[
    {{p:25,val:pct(sorted,25),color:"#58a6ff",dash:"dot"}},
    {{p:50,val:pct(sorted,50),color:"#3fb950",dash:"dash"}},
    {{p:75,val:pct(sorted,75),color:"#f5a623",dash:"dash"}},
    {{p:90,val:pct(sorted,90),color:"#ef5350",dash:"dot"}},
  ];

  const shapes=[];
  const annotations=[];
  for(let si=0;si<msX.length;){{
    let ei=si;
    while(ei+1<msX.length&&msENSO[ei+1]===msENSO[si])ei++;
    if(ENSO_FILL[msENSO[si]]){{
      const x1=ei+1<msX.length?msX[ei+1]
        :new Date(new Date(msX[ei]).setMonth(new Date(msX[ei]).getMonth()+1)).toISOString().slice(0,10);
      shapes.push({{type:"rect",layer:"below",xref:"x",yref:"paper",
        x0:msX[si],x1,y0:0,y1:1,fillcolor:ENSO_FILL[msENSO[si]],line:{{width:0}}}});
    }}
    si=ei+1;
  }}
  for(const {{p,val,color,dash}} of PCT_LINES){{
    shapes.push({{type:"line",xref:"paper",yref:"y",x0:0,x1:1,y0:val,y1:val,
      layer:"above",line:{{color,dash,width:1.2}}}});
    annotations.push({{xref:"paper",yref:"y",x:1.0,y:val,
      text:"P"+p,showarrow:false,
      font:{{color,size:9}},xanchor:"left",yanchor:"middle",
      bgcolor:"rgba(13,17,23,0.7)",borderpad:2}});
  }}

  const rc = REGION_CONFIG[currentRegion];
  const allLabel = rc.all_label;
  const label = stateKey==="all" ? allLabel : stateKey;
  document.getElementById("lineTitle").textContent =
    "Monthly Precipitation — "+label+" ("+YR0+"–"+YR1+")";
  Plotly.react("lineDiv",[
    {{type:"scatter",mode:"lines",x:msX,y:msY,
      line:{{color:"#f5a623",width:1.5}},fill:"tozeroy",
      fillcolor:"rgba(245,166,35,0.07)",customdata:msENSO,
      hovertemplate:"<b>%{{x|%b %Y}}</b><br>%{{y:.1f}} mm<br>%{{customdata}}<extra></extra>",
      showlegend:false}},
    {{type:"scatter",x:[null],y:[null],mode:"markers",name:"El Niño",
      marker:{{color:"rgba(239,83,80,0.7)",symbol:"square",size:11}},showlegend:true}},
    {{type:"scatter",x:[null],y:[null],mode:"markers",name:"La Niña",
      marker:{{color:"rgba(30,136,229,0.7)",symbol:"square",size:11}},showlegend:true}},
    {{type:"scatter",x:[null],y:[null],mode:"markers",name:"Neutral",
      marker:{{color:"rgba(139,148,158,0.5)",symbol:"square",size:11}},showlegend:true}},
  ],{{
    autosize:true,paper_bgcolor:DARK.paper,plot_bgcolor:DARK.paper,height:280,
    margin:{{l:55,r:45,t:15,b:40}},shapes,annotations,
    xaxis:{{type:"date",dtick:"M60",tickformat:"%Y",color:DARK.muted,gridcolor:DARK.grid}},
    yaxis:{{title:"mm / month",rangemode:"tozero",color:DARK.muted,gridcolor:DARK.grid}},
    legend:{{x:0.01,y:0.99,font:{{color:DARK.text,size:11}},
             bgcolor:DARK.card,bordercolor:DARK.border,borderwidth:1}}
  }},{{responsive:true}});
}}

// ── Climatology ───────────────────────────────────────────────────────────────
function renderClimatology(stateKey) {{
  const rows=stateRows[stateKey]||[];
  const byPhase={{}};
  for(const ph of ENSO_PHASES) byPhase[ph]=Array.from({{length:12}},()=>({{s:0,n:0}}));
  for(const r of rows){{
    const ph=r.enso; if(!byPhase[ph]) continue;
    byPhase[ph][+r.month-1].s+=+r.prcp_mm; byPhase[ph][+r.month-1].n++;
  }}
  const rc = REGION_CONFIG[currentRegion];
  const allLabel = rc.all_label;
  const label = stateKey==="all" ? allLabel : stateKey;
  document.getElementById("climTitle").textContent =
    "Monthly Climatology — "+label+" by ENSO Phase";
  Plotly.react("climDiv",
    ENSO_PHASES.map((ph,i)=>({{
      type:"bar",name:ph,x:MONTH_NAMES,
      y:byPhase[ph].map(d=>d.n?+(d.s/d.n).toFixed(1):0),
      marker:{{color:ENSO_COLORS[i],opacity:0.85}},
      hovertemplate:"<b>%{{x}} — "+ph+"</b><br>%{{y:.1f}} mm avg<extra></extra>"
    }})),
  {{
    autosize:true,barmode:"group",
    paper_bgcolor:DARK.paper,plot_bgcolor:DARK.paper,height:260,
    margin:{{l:50,r:20,t:10,b:40}},
    xaxis:{{color:DARK.muted,gridcolor:DARK.grid}},
    yaxis:{{title:"mm",color:DARK.muted,gridcolor:DARK.grid}},
    legend:{{font:{{color:DARK.text,size:11}},bgcolor:DARK.card,bordercolor:DARK.border,borderwidth:1}}
  }},{{responsive:true}});
}}

// ── Load region ───────────────────────────────────────────────────────────────
async function loadRegion(key) {{
  const rc = REGION_CONFIG[key];
  currentRegion = key;
  const initialLoad = document.getElementById("content").style.display !== "block";

  // Show loading state
  if (initialLoad) {{
    document.getElementById("loading").textContent = "Loading "+rc.name+" data…";
    document.getElementById("loading").style.display = "block";
  }} else {{
    Plotly.purge("mapDiv");
    document.getElementById("mapDiv").innerHTML =
      "<div style='height:440px;display:flex;align-items:center;justify-content:center;color:var(--muted)'>Loading "+rc.name+"…</div>";
  }}

  // Fetch CSV (cached after first load)
  if (!csvCache[key]) {{
    try {{
      const resp = await fetch(rc.csv);
      if (!resp.ok) throw new Error(
        rc.name+" data not yet available — run convert_global_precipitation.py locally and commit the CSV files.");
      csvCache[key] = await resp.text();
    }} catch(e) {{
      const msg = e.message;
      if (initialLoad) {{
        document.getElementById("loading").innerHTML =
          "<p style='color:var(--muted);max-width:480px;margin:auto'>"+msg+"</p>";
      }} else {{
        document.getElementById("mapDiv").innerHTML =
          "<div style='height:440px;display:flex;align-items:center;justify-content:center;padding:2rem;text-align:center'>"
          +"<p style='color:var(--muted);font-size:.85rem'>"+msg+"</p></div>";
      }}
      return;
    }}
  }}

  const rows = parseCSV(csvCache[key]);

  // ── Reset mutable state ───────────────────────────────────────────────────
  fixedLats=[]; fixedLons=[]; cellList=[];
  monthlyData={{}}; sortedKeys=[]; composites={{}};
  stateRows={{}}; cachedSliderSteps=[]; cmapMax=100;
  currentMode="tracker";

  // ── 1. Fixed ordered cell list ────────────────────────────────────────────
  const cellSet=new Set();
  for(const r of rows) cellSet.add(r.lat+","+r.lon);
  cellList=[...cellSet].sort();
  fixedLats=cellList.map(k=>+k.split(",")[0]);
  fixedLons=cellList.map(k=>+k.split(",")[1]);
  const cellIdx=Object.fromEntries(cellList.map((k,i)=>[k,i]));
  const nCells=cellList.length;

  // ── 2. Group rows by sub-region and by month ──────────────────────────────
  stateRows["all"]=rows;
  for(const r of rows){{
    if(!stateRows[r.state]) stateRows[r.state]=[];
    stateRows[r.state].push(r);
  }}

  // ── 3. Per-month ordered value arrays ─────────────────────────────────────
  const rawMonthly={{}};
  for(const r of rows){{
    const k=r.year+"-"+r.month.padStart(2,"0");
    if(!rawMonthly[k]) rawMonthly[k]={{vals:new Array(nCells).fill(null),enso:r.enso,year:+r.year,month:+r.month}};
    const ci=cellIdx[r.lat+","+r.lon];
    if(ci!==undefined) rawMonthly[k].vals[ci]=+r.prcp_mm;
  }}
  sortedKeys=Object.keys(rawMonthly).sort();
  for(const k of sortedKeys) monthlyData[k]=rawMonthly[k];

  // ── 4. Colorscale cap: 95th percentile ───────────────────────────────────
  const allVals=[];
  for(const k of sortedKeys) for(const v of monthlyData[k].vals) if(v!==null) allVals.push(v);
  allVals.sort((a,b)=>a-b);
  cmapMax=Math.round(allVals[Math.floor(allVals.length*0.95)]/10)*10||100;

  // ── 5. ENSO composites ────────────────────────────────────────────────────
  function buildComposite(phase){{
    const S=new Array(nCells).fill(0),N=new Array(nCells).fill(0);
    const ks=phase==="all"?sortedKeys:sortedKeys.filter(k=>monthlyData[k].enso===phase);
    for(const k of ks){{
      const vals=monthlyData[k].vals;
      for(let i=0;i<nCells;i++){{ if(vals[i]!==null){{S[i]+=vals[i];N[i]++;}} }}
    }}
    return S.map((s,i)=>N[i]>0?+(s/N[i]).toFixed(1):null);
  }}
  for(const ph of ["all",...ENSO_PHASES]) composites[ph]=buildComposite(ph);

  // ── 6. Slider steps ───────────────────────────────────────────────────────
  cachedSliderSteps=sortedKeys.map(k=>{{
    const fd=monthlyData[k];
    return {{
      args:[[k],{{frame:{{duration:250,redraw:true}},mode:"immediate",transition:{{duration:80}}}}],
      label:fd.month===1?String(fd.year):"",
      method:"animate",
    }};
  }});

  // ── 7. Update UI labels and sub-region pills ──────────────────────────────
  YR0=sortedKeys[0].split("-")[0];
  YR1=sortedKeys[sortedKeys.length-1].split("-")[0];
  document.getElementById("pageTitle").textContent=rc.name+" Precipitation";
  document.getElementById("pageSubtitle").innerHTML=rc.source_html+" · "+YR0+"–"+YR1;
  document.getElementById("subregionHeader").textContent="Select "+rc.subregion_label;

  const subregions=[...new Set(rows.map(r=>r.state))].sort();
  const sel=document.getElementById("stateSelector");
  let pillsHtml=`<button class="btn active" data-state="all">${{rc.all_label}}</button>`;
  for(const s of subregions) pillsHtml+=`<button class="btn" data-state="${{s}}">${{s}}</button>`;
  sel.innerHTML=pillsHtml;

  // Reset tabs and ENSO toggle to defaults
  document.querySelectorAll(".tab").forEach(b=>b.classList.remove("active"));
  document.querySelector("[data-tab='tracker']").classList.add("active");
  document.querySelectorAll("#ensoToggle .btn").forEach(b=>b.classList.remove("active"));
  document.querySelector("[data-enso='all']").classList.add("active");
  document.getElementById("trackerDesc").style.display="";
  document.getElementById("compositeControls").style.display="none";

  // ── 8. Show content and render map ───────────────────────────────────────
  if(initialLoad){{
    document.getElementById("loading").style.display="none";
    document.getElementById("content").style.display="block";
  }} else {{
    document.getElementById("mapDiv").innerHTML="";
  }}

  const fd0=monthlyData[sortedKeys[0]];
  await Plotly.newPlot(
    "mapDiv",
    [makeTrace(fd0.vals)],
    makeTrackerLayout(fd0,cachedSliderSteps),
    {{responsive:true}}
  );

  // ── 9. Animation frames (only marker.color changes per frame) ─────────────
  const frames=sortedKeys.map(k=>{{
    const fd=monthlyData[k];
    return {{
      name:k,
      data:[{{marker:{{color:fd.vals}}}}],
      traces:[0],
      layout:{{annotations:trackerAnnotations(fd)}},
    }};
  }});
  await Plotly.addFrames("mapDiv",frames);

  // ── 10. Charts ────────────────────────────────────────────────────────────
  renderTimeSeries("all");
  renderClimatology("all");
}}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {{
  await loadRegion("usa");
}}

init().catch(err=>{{
  document.getElementById("loading").innerHTML=
    "<p style='color:var(--muted)'>Error loading data: "+err.message+"</p>";
}});
</script>
</body>
</html>
"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html, encoding="utf-8")
    size_kb = Path(output_path).stat().st_size // 1024
    print(f"Precipitation page written → {output_path}  ({size_kb} KB)")


if __name__ == "__main__":
    from fetch_precipitation import fetch_precipitation_data
    meta = fetch_precipitation_data()
    render_precipitation(meta)
