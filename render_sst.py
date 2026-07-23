"""
render_sst.py
Generates docs/sst.html — Sea Surface Temperature Anomaly dashboard.
Data: docs/data/sst_grid.csv  (from convert_sst.py)
"""

import json
from pathlib import Path

META_FILE = Path("docs/data/sst_meta.json")

# Diverging blue (cold) → white (neutral) → red (warm)
SST_SCALE = [
    [0.00, "#053061"],
    [0.12, "#2166ac"],
    [0.25, "#4393c3"],
    [0.38, "#92c5de"],
    [0.47, "#d1e5f0"],
    [0.50, "#f7f7f7"],
    [0.53, "#fddbc7"],
    [0.62, "#f4a582"],
    [0.75, "#d6604d"],
    [0.88, "#b2182b"],
    [1.00, "#67001f"],
]

_SCALE_JSON = json.dumps(SST_SCALE)


def render_sst(output_path: str = "docs/sst.html") -> None:
    meta = {}
    if META_FILE.exists():
        with open(META_FILE) as f:
            meta = json.load(f)

    first = meta.get("first_month", "1970-01")
    last  = meta.get("last_month",  "2026-06")
    yr0   = first[:4]
    yr1   = last[:4]
    basins = meta.get("basins", [
        "Niño 3.4", "Tropical Pacific", "Tropical Atlantic",
        "Indian Ocean", "North Pacific", "North Atlantic",
        "Southern Ocean", "Global",
    ])

    basins_json = json.dumps(basins)

    # Build year/month lists for difference dropdowns
    y0i, m0i = int(yr0), 1
    y1i, m1i = int(yr1), int(last[5:7])
    date_options = []
    y, m = y0i, m0i
    while (y, m) <= (y1i, m1i):
        date_options.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    dates_json = json.dumps(date_options)
    default_date1 = date_options[max(0, len(date_options) - 13)]
    default_date2 = date_options[-1]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sea Surface Temperature Tracker</title>
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
  .nav-links a.nav-active {{ color:#fff; background:#0ea5e9; font-weight:600; }}
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
  .diff-row {{ display:flex; align-items:center; gap:.75rem; flex-wrap:wrap;
               margin-bottom:.8rem; }}
  .diff-row label {{ font-size:.8rem; color:var(--muted); }}
  .diff-row select {{ background:#1c2128; border:1px solid var(--border); color:var(--text);
                      padding:.3rem .6rem; border-radius:5px; font-size:.8rem; cursor:pointer; }}
  .diff-row select:focus {{ outline:none; border-color:#388bfd; }}
  #diffBtn {{ background:#0ea5e9; border:none; color:#fff; padding:.35rem 1rem;
              border-radius:6px; font-size:.8rem; cursor:pointer; font-weight:600; }}
  #diffBtn:hover {{ background:#0284c7; }}
</style>
</head>
<body>

<nav class="topnav">
  <a class="nav-brand" href="index.html">ENSO Tracker</a>
  <div class="nav-links">
    <a href="index.html">ENSO Dashboard</a>
    <a href="hurricanes.html">Cyclone Tracker</a>
    <a href="precipitation.html">Precipitation</a>
    <a href="temperature.html">Land Temp</a>
    <a href="sst.html" class="nav-active">Sea Surface Temp</a>
  </div>
</nav>

<h1>Sea Surface Temperature Anomaly</h1>
<p class="subtitle">
  NOAA ERSST v5 · 8° grid · Anomaly vs 1991–2020 climatology ·
  <a href="https://psl.noaa.gov/data/gridded/data.noaa.ersst.v5.html" target="_blank">NOAA/PSL</a>
  · {yr0}–{yr1}
</p>

<div id="loading" style="text-align:center;padding:3rem;color:var(--muted)">
  Loading SST data&hellip;
</div>

<div id="content">

  <div class="card">
    <h2>SST Anomaly Map</h2>

    <div class="tab-row" id="mapTabs">
      <button class="tab active" data-tab="tracker">Monthly Tracker</button>
      <button class="tab"        data-tab="composite">ENSO Composite</button>
      <button class="tab"        data-tab="diff">Difference Map</button>
    </div>

    <div id="trackerDesc">
      <p style="font-size:.78rem;color:var(--muted);margin-bottom:.5rem">
        Monthly SST anomaly (°C) vs 1991–2020 baseline.
        Red&nbsp;=&nbsp;warmer than normal · Blue&nbsp;=&nbsp;cooler than normal.
        Use &#9654; Play or drag the slider to animate.
      </p>
    </div>

    <div id="compositeControls" style="display:none">
      <p style="font-size:.78rem;color:var(--muted);margin-bottom:.5rem">
        Average SST anomaly per ENSO phase. Toggle to compare spatial patterns.
      </p>
      <div class="btn-row" id="ensoToggle">
        <button class="btn active" data-enso="all">All Years</button>
        <button class="btn" data-enso="El Ni&ntilde;o">El Ni&ntilde;o</button>
        <button class="btn" data-enso="La Ni&ntilde;a">La Ni&ntilde;a</button>
        <button class="btn" data-enso="Neutral">Neutral</button>
      </div>
    </div>

    <div id="diffControls" style="display:none">
      <p style="font-size:.78rem;color:var(--muted);margin-bottom:.6rem">
        Difference = SST[Date 2] &minus; SST[Date 1]. Red = warmer in Date 2.
      </p>
      <div class="diff-row">
        <label>Date 1:</label>
        <select id="diffDate1"></select>
        <label>Date 2:</label>
        <select id="diffDate2"></select>
        <button id="diffBtn">Plot Difference</button>
      </div>
    </div>

    <div id="mapDiv" style="height:540px;width:100%"></div>
  </div>

  <div class="card" style="padding:.75rem 1rem;margin-bottom:1rem">
    <div style="display:flex;align-items:center;gap:.8rem;flex-wrap:wrap">
      <span style="font-size:.78rem;color:var(--muted);font-weight:600;white-space:nowrap">Ocean Basin:</span>
      <div class="btn-row" id="basinSelector" style="margin:0"></div>
    </div>
  </div>

  <div class="card">
    <h2 id="lineTitle">Monthly SST Anomaly — Global ({yr0}–{yr1})</h2>
    <p style="font-size:.78rem;color:var(--muted);margin-bottom:.5rem">
      Area-average SST anomaly (°C) for selected basin.
      <span style="background:rgba(239,83,80,.22);padding:1px 5px;border-radius:3px">El Ni&ntilde;o</span>
      and
      <span style="background:rgba(30,136,229,.22);padding:1px 5px;border-radius:3px">La Ni&ntilde;a</span>
      periods shaded.
    </p>
    <div id="lineDiv"></div>
  </div>

  <div class="card">
    <h2 id="climTitle">SST Anomaly by Month and ENSO Phase — Global</h2>
    <p style="font-size:.78rem;color:var(--muted);margin-bottom:.5rem">
      Average SST anomaly per calendar month, split by ENSO phase.
    </p>
    <div id="climDiv"></div>
  </div>

</div>

<footer>
  ENSO: <a href="https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt" target="_blank">NOAA/CPC ONI</a>
  &nbsp;&middot;&nbsp; SST: <a href="https://psl.noaa.gov/data/gridded/data.noaa.ersst.v5.html" target="_blank">NOAA ERSST v5</a>
  &nbsp;&middot;&nbsp; <a href="precipitation.html">🌧 Precipitation →</a>
  &nbsp;&middot;&nbsp; <a href="temperature.html">🌡 Land Temp →</a>
</footer>

<script>
const SST_SCALE   = {_SCALE_JSON};
const ALL_BASINS  = {basins_json};
const DATE_LIST   = {dates_json};
const DEFAULT_D1  = "{default_date1}";
const DEFAULT_D2  = "{default_date2}";
const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const DARK = {{
  paper:"#0d1117", plot:"#0d1117", text:"#c9d1d9",
  muted:"#8b949e", grid:"#21262d", card:"#1c2128", border:"#30363d"
}};
const ENSO_PHASES = ["El Niño","Neutral","La Niña"];
const ENSO_COLORS = ["#ef5350","#8b949e","#1e88e5"];
const ENSO_FILL   = {{"El Niño":"rgba(239,83,80,0.18)","La Niña":"rgba(30,136,229,0.18)"}};
const ANOM_MIN = -3, ANOM_MAX = 3;
const MARKER_SIZE = 12;   // square markers on Robinson 8° grid

let currentMode   = "tracker";
let currentBasin  = "Global";
let fixedLats     = [];
let fixedLons     = [];
let fixedBasins   = [];
let cellList      = [];
let monthlyData   = {{}};   // key "YYYY-MM" -> {{vals, enso, year, month}}
let sortedKeys    = [];
let composites    = {{}};
let basinRows     = {{}};   // basin -> {{years,months,ssts,ensos}} sliced
let cachedSliderSteps = [];

// ── Fast CSV parser — uses indexOf per column, avoids object-per-row alloc ────
function parseSST(text) {{
  const nl   = text.indexOf('\\n'); // end of header line
  let pos    = nl + 1;
  const n    = text.split('\\n').length - 1;
  const years  = new Int16Array(n);
  const months = new Uint8Array(n);
  const lats   = new Float32Array(n);
  const lons   = new Float32Array(n);
  const ssts   = new Float32Array(n);
  const ensos  = [];
  const basins = [];
  let i = 0;
  while (pos < text.length) {{
    const end = text.indexOf('\\n', pos);
    const line = end === -1 ? text.slice(pos) : text.slice(pos, end);
    pos = end === -1 ? text.length : end + 1;
    if (!line.trim()) continue;
    let p0 = line.indexOf(',');
    let p1 = line.indexOf(',', p0+1);
    let p2 = line.indexOf(',', p1+1);
    let p3 = line.indexOf(',', p2+1);
    let p4 = line.indexOf(',', p3+1);
    let p5 = line.indexOf(',', p4+1);
    years[i]  = +line.slice(0, p0);
    months[i] = +line.slice(p0+1, p1);
    lats[i]   = +line.slice(p1+1, p2);
    lons[i]   = +line.slice(p2+1, p3);
    ssts[i]   = +line.slice(p3+1, p4);
    ensos.push(line.slice(p4+1, p5));
    basins.push(line.slice(p5+1).trim());
    i++;
  }}
  return {{ years:years.slice(0,i), months:months.slice(0,i),
            lats:lats.slice(0,i), lons:lons.slice(0,i),
            ssts:ssts.slice(0,i), ensos, basins, n:i }};
}}

// ── Map trace (scattergeo — true global projection, no world tiling) ──────────
function makeTrace(vals, cmin, cmax, titleText) {{
  return {{
    type:"scattergeo", mode:"markers",
    lat:fixedLats, lon:fixedLons,
    customdata:fixedBasins,
    marker:{{
      size:MARKER_SIZE, symbol:"square", opacity:0.92,
      color:vals,
      colorscale:SST_SCALE,
      cmin: cmin ?? ANOM_MIN,
      cmax: cmax ?? ANOM_MAX,
      line:{{width:0.5, color:"#0d1117"}},
      colorbar:{{
        title:{{text: titleText ?? "°C anom", font:{{color:DARK.muted,size:11}}}},
        tickfont:{{color:DARK.muted,size:10}},
        bgcolor:"rgba(12,17,23,0.80)",bordercolor:DARK.border,borderwidth:1,
        len:0.55,thickness:14,x:1.01,xpad:8,
        tickvals:[-3,-2,-1,0,1,2,3],
        ticktext:["-3","-2","-1","0","+1","+2","+3"],
      }}
    }},
    hovertemplate:"<b>%{{customdata}}</b><br>%{{lat:.1f}}°, %{{lon:.1f}}°<br>%{{marker.color:+.2f}} °C<extra></extra>",
    showlegend:false
  }};
}}

function makeBaseLayout(withSlider) {{
  return {{
    autosize:true,
    paper_bgcolor:DARK.paper,
    uirevision:"sst-map",
    geo:{{
      showland:true,       landcolor:"#1c2128",
      showocean:true,      oceancolor:"#0d1117",
      showcoastlines:true, coastlinecolor:"#4a5568",
      showframe:false,
      showcountries:false,
      projection:{{type:"robinson"}},
      bgcolor:"#0d1117",
      lataxis:{{range:[-80,85]}},
    }},
    margin:{{l:0, r:65, t:0, b: withSlider ? 130 : 20}},
  }};
}}

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

function phaseAnnotation(label) {{
  return [{{text:label, x:0.01,y:0.97,xref:"paper",yref:"paper",
    xanchor:"left",yanchor:"top",showarrow:false,
    font:{{size:16,color:"#e6edf3",family:"monospace",weight:700}},
    bgcolor:"rgba(13,17,23,0.75)",borderpad:4}}];
}}

function makeTrackerLayout(fd, sliderSteps) {{
  return {{
    ...makeBaseLayout(true),
    annotations:trackerAnnotations(fd),
    updatemenus:[{{
      type:"buttons", showactive:false,
      x:0.01, y:-0.08, xanchor:"left", yanchor:"top",
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
      x:0.12, y:-0.05, xanchor:"left", yanchor:"top", len:0.86,
      currentvalue:{{visible:false}},
      transition:{{duration:80}},
      bgcolor:"#21262d", bordercolor:"#30363d",
      tickcolor:"#8b949e", font:{{color:DARK.muted,size:9}},
      pad:{{b:10,t:55}}, minorticklen:0,
    }}],
  }};
}}

function makeStaticLayout(label) {{
  return {{
    ...makeBaseLayout(false),
    annotations:phaseAnnotation(label),
    updatemenus:[], sliders:[],
  }};
}}

// ── Basin selector ─────────────────────────────────────────────────────────────
function buildBasinSelector() {{
  const sel = document.getElementById("basinSelector");
  sel.innerHTML = ALL_BASINS.map(b =>
    `<button class="btn${{b===currentBasin?" active":""}}" data-basin="${{b}}">${{b}}</button>`
  ).join("");
}}

document.getElementById("basinSelector").addEventListener("click", e => {{
  const btn = e.target.closest("[data-basin]");
  if (!btn) return;
  document.querySelectorAll("#basinSelector .btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  currentBasin = btn.dataset.basin;
  renderTimeSeries(currentBasin);
  renderClimatology(currentBasin);
}});

// ── Map tab switching ──────────────────────────────────────────────────────────
document.getElementById("mapTabs").addEventListener("click", e => {{
  const btn = e.target.closest("[data-tab]");
  if (!btn || btn.dataset.tab === currentMode) return;
  document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  currentMode = btn.dataset.tab;
  document.getElementById("trackerDesc").style.display       = currentMode==="tracker"   ? "" : "none";
  document.getElementById("compositeControls").style.display = currentMode==="composite" ? "" : "none";
  document.getElementById("diffControls").style.display      = currentMode==="diff"      ? "" : "none";
  if (currentMode === "tracker") {{
    const fd = monthlyData[sortedKeys[0]];
    Plotly.react("mapDiv",[makeTrace(fd.vals)],makeTrackerLayout(fd,cachedSliderSteps),{{responsive:true}});
    Plotly.addFrames("mapDiv", buildFrames());
  }} else if (currentMode === "composite") {{
    const phase = document.querySelector("#ensoToggle .btn.active")?.dataset.enso || "all";
    Plotly.react("mapDiv",[makeTrace(composites[phase])],makeStaticLayout(phase==="all"?"All Years":phase),{{responsive:true}});
  }} else {{
    Plotly.react("mapDiv",[makeTrace(composites["all"])],makeStaticLayout("Select dates → Plot Difference"),{{responsive:true}});
  }}
}});

document.getElementById("ensoToggle").addEventListener("click", e => {{
  const btn = e.target.closest("[data-enso]");
  if (!btn) return;
  document.querySelectorAll("#ensoToggle .btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  const phase = btn.dataset.enso;
  Plotly.react("mapDiv",[makeTrace(composites[phase])],makeStaticLayout(phase==="all"?"All Years":phase),{{responsive:true}});
}});

// ── Difference map ─────────────────────────────────────────────────────────────
function buildDateDropdowns() {{
  const s1 = document.getElementById("diffDate1");
  const s2 = document.getElementById("diffDate2");
  const opts = DATE_LIST.map(d => `<option value="${{d}}">${{d}}</option>`).join("");
  s1.innerHTML = opts;
  s2.innerHTML = opts;
  s1.value = DEFAULT_D1;
  s2.value = DEFAULT_D2;
}}

document.getElementById("diffBtn").addEventListener("click", () => {{
  const d1 = document.getElementById("diffDate1").value;
  const d2 = document.getElementById("diffDate2").value;
  const fd1 = monthlyData[d1], fd2 = monthlyData[d2];
  if (!fd1 || !fd2) {{ alert("One or both dates not in dataset."); return; }}
  const diff = fd1.vals.map((a,i) => (isNaN(a)||isNaN(fd2.vals[i])) ? null : +(fd2.vals[i]-a).toFixed(2));
  const maxAbs = Math.max(...diff.filter(x=>x!==null).map(Math.abs));
  const bound  = Math.min(Math.ceil(maxAbs*10)/10, 5);
  Plotly.react("mapDiv",[makeTrace(diff,-bound,bound,"°C diff")],
    makeStaticLayout(`${{d2}} minus ${{d1}}`),{{responsive:true}});
}});

// ── Time series ────────────────────────────────────────────────────────────────
function renderTimeSeries(basin) {{
  const br = basinRows[basin] || basinRows["Global"];
  const mdata = {{}};
  for (let i=0; i<br.n; i++) {{
    const k = br.years[i]+"-"+String(br.months[i]).padStart(2,"0");
    if (!mdata[k]) mdata[k] = {{s:0,c:0,enso:br.ensos[i],year:br.years[i],month:br.months[i]}};
    mdata[k].s += br.ssts[i]; mdata[k].c++;
  }}
  const keys   = Object.keys(mdata).sort();
  const msX    = keys.map(k => {{ const d=mdata[k]; return d.year+"-"+String(d.month).padStart(2,"0")+"-01"; }});
  const msY    = keys.map(k => +(mdata[k].s/mdata[k].c).toFixed(3));
  const msENSO = keys.map(k => mdata[k].enso);

  const shapes=[];
  for (let si=0; si<msX.length;) {{
    let ei=si;
    while(ei+1<msX.length && msENSO[ei+1]===msENSO[si]) ei++;
    if (ENSO_FILL[msENSO[si]]) {{
      const x1 = ei+1<msX.length ? msX[ei+1]
        : new Date(new Date(msX[ei]).setMonth(new Date(msX[ei]).getMonth()+1)).toISOString().slice(0,10);
      shapes.push({{type:"rect",layer:"below",xref:"x",yref:"paper",
        x0:msX[si],x1,y0:0,y1:1,fillcolor:ENSO_FILL[msENSO[si]],line:{{width:0}}}});
    }}
    si=ei+1;
  }}
  shapes.push({{type:"line",xref:"paper",yref:"y",x0:0,x1:1,y0:0,y1:0,
    layer:"above",line:{{color:"#8b949e",dash:"dot",width:1}}}});

  document.getElementById("lineTitle").textContent =
    "Monthly SST Anomaly — "+basin+" ({yr0}–{yr1})";

  Plotly.react("lineDiv",[
    {{type:"scatter",mode:"lines",x:msX,y:msY,
      fill:"tozeroy",fillcolor:"rgba(14,165,233,0.12)",
      line:{{color:"#0ea5e9",width:1.5}},
      customdata:msENSO,
      hovertemplate:"<b>%{{x|%b %Y}}</b><br>%{{y:+.3f}} °C<br>%{{customdata}}<extra></extra>",
      showlegend:false}},
    {{type:"scatter",x:[null],y:[null],mode:"markers",name:"El Niño",
      marker:{{color:"rgba(239,83,80,0.7)",symbol:"square",size:11}},showlegend:true}},
    {{type:"scatter",x:[null],y:[null],mode:"markers",name:"La Niña",
      marker:{{color:"rgba(30,136,229,0.7)",symbol:"square",size:11}},showlegend:true}},
    {{type:"scatter",x:[null],y:[null],mode:"markers",name:"Neutral",
      marker:{{color:"rgba(139,148,158,0.5)",symbol:"square",size:11}},showlegend:true}},
  ],{{
    autosize:true,paper_bgcolor:DARK.paper,plot_bgcolor:DARK.paper,height:280,
    margin:{{l:55,r:40,t:15,b:40}},shapes,
    xaxis:{{type:"date",dtick:"M60",tickformat:"%Y",color:DARK.muted,gridcolor:DARK.grid}},
    yaxis:{{title:"°C anomaly",color:DARK.muted,gridcolor:DARK.grid,zeroline:false}},
    legend:{{x:0.01,y:0.99,font:{{color:DARK.text,size:11}},
             bgcolor:DARK.card,bordercolor:DARK.border,borderwidth:1}}
  }},{{responsive:true}});
}}

// ── Climatology ────────────────────────────────────────────────────────────────
function renderClimatology(basin) {{
  const br = basinRows[basin] || basinRows["Global"];
  const byPhase = {{}};
  for (const ph of ENSO_PHASES) byPhase[ph] = Array.from({{length:12}},()=>({{s:0,n:0}}));
  for (let i=0; i<br.n; i++) {{
    const ph = br.ensos[i]; if (!byPhase[ph]) continue;
    byPhase[ph][br.months[i]-1].s += br.ssts[i]; byPhase[ph][br.months[i]-1].n++;
  }}
  document.getElementById("climTitle").textContent =
    "SST Anomaly by Month and ENSO Phase — "+basin;
  Plotly.react("climDiv",
    ENSO_PHASES.map((ph,i) => ({{
      type:"bar",name:ph,x:MONTH_NAMES,
      y:byPhase[ph].map(d=>d.n?+(d.s/d.n).toFixed(3):null),
      marker:{{color:ENSO_COLORS[i],opacity:0.85}},
      hovertemplate:"<b>%{{x}} — "+ph+"</b><br>%{{y:+.3f}} °C<extra></extra>"
    }})),
  {{
    autosize:true,barmode:"group",
    paper_bgcolor:DARK.paper,plot_bgcolor:DARK.paper,height:260,
    margin:{{l:55,r:20,t:10,b:40}},
    xaxis:{{color:DARK.muted,gridcolor:DARK.grid}},
    yaxis:{{title:"°C anomaly",color:DARK.muted,gridcolor:DARK.grid,
            zeroline:true,zerolinecolor:DARK.grid}},
    legend:{{font:{{color:DARK.text,size:11}},bgcolor:DARK.card,bordercolor:DARK.border,borderwidth:1}}
  }},{{responsive:true}});
}}

// ── Animation frames ───────────────────────────────────────────────────────────
function buildFrames() {{
  return sortedKeys.map(k => {{
    const fd = monthlyData[k];
    return {{
      name:k,
      data:[{{marker:{{color:fd.vals}}}}],
      traces:[0],
      layout:{{annotations:trackerAnnotations(fd)}},
    }};
  }});
}}

// ── Init ───────────────────────────────────────────────────────────────────────
async function init() {{
  document.getElementById("loading").textContent = "Loading SST data (23 MB)…";

  let data;
  try {{
    const resp = await fetch("data/sst_grid.csv");
    if (!resp.ok) throw new Error(
      "SST data not available — run convert_sst.py and commit docs/data/sst_grid.csv");
    document.getElementById("loading").textContent = "Parsing data…";
    // Yield to browser so loading message updates before blocking parse
    await new Promise(r => setTimeout(r, 30));
    const text = await resp.text();
    data = parseSST(text);
  }} catch(e) {{
    document.getElementById("loading").innerHTML =
      "<p style='color:var(--muted);max-width:480px;margin:auto'>"+e.message+"</p>";
    return;
  }}

  // ── Build cell index ──────────────────────────────────────────────────────
  const cellKeySet = new Set();
  const cellBasinMap = {{}};
  for (let i=0; i<data.n; i++) {{
    const k = data.lats[i]+","+data.lons[i];
    if (!cellKeySet.has(k)) {{
      cellKeySet.add(k);
      cellBasinMap[k] = data.basins[i];
    }}
  }}
  cellList    = [...cellKeySet].sort();
  fixedLats   = cellList.map(k => +k.split(",")[0]);
  fixedLons   = cellList.map(k => +k.split(",")[1]);
  fixedBasins = cellList.map(k => cellBasinMap[k] || "");
  const cellIdx = Object.fromEntries(cellList.map((k,i) => [k,i]));
  const nCells  = cellList.length;

  // ── Build monthly data in single pass ─────────────────────────────────────
  document.getElementById("loading").textContent = "Building charts…";
  await new Promise(r => setTimeout(r, 30));

  const rawMonthly = {{}};
  for (let i=0; i<data.n; i++) {{
    const k = data.years[i]+"-"+String(data.months[i]).padStart(2,"0");
    if (!rawMonthly[k]) rawMonthly[k] = {{
      vals:new Array(nCells).fill(null),
      enso:data.ensos[i], year:data.years[i], month:data.months[i]
    }};
    const ci = cellIdx[data.lats[i]+","+data.lons[i]];
    if (ci !== undefined) rawMonthly[k].vals[ci] = data.ssts[i];
  }}
  sortedKeys = Object.keys(rawMonthly).sort();
  for (const k of sortedKeys) monthlyData[k] = rawMonthly[k];

  // ── Build basin row slices ─────────────────────────────────────────────────
  // For each basin, store index arrays into the typed arrays
  const basinIdxMap = {{}};
  for (let i=0; i<data.n; i++) {{
    const b = data.basins[i];
    if (!basinIdxMap[b]) basinIdxMap[b] = [];
    basinIdxMap[b].push(i);
  }}
  // Global = all rows
  basinRows["Global"] = data;
  // Per-basin: build mini typed arrays
  for (const [b, idxs] of Object.entries(basinIdxMap)) {{
    if (b === "Global") continue;
    const n = idxs.length;
    const br = {{
      years:  new Int16Array(n), months: new Uint8Array(n),
      ssts:   new Float32Array(n), ensos: [], basins: [], n
    }};
    for (let j=0; j<n; j++) {{
      const i = idxs[j];
      br.years[j]=data.years[i]; br.months[j]=data.months[i];
      br.ssts[j]=data.ssts[i];   br.ensos.push(data.ensos[i]);
      br.basins.push(data.basins[i]);
    }}
    basinRows[b] = br;
  }}

  // ── Build composites ───────────────────────────────────────────────────────
  function buildComposite(phase) {{
    const S=new Array(nCells).fill(0), N=new Array(nCells).fill(0);
    const ks = phase==="all" ? sortedKeys : sortedKeys.filter(k=>monthlyData[k].enso===phase);
    for (const k of ks) {{
      const vals = monthlyData[k].vals;
      for (let i=0;i<nCells;i++) {{ if(vals[i]!==null){{S[i]+=vals[i];N[i]++;}} }}
    }}
    return S.map((s,i)=>N[i]>0?+(s/N[i]).toFixed(3):null);
  }}
  for (const ph of ["all",...ENSO_PHASES]) composites[ph] = buildComposite(ph);

  // ── Slider steps ───────────────────────────────────────────────────────────
  cachedSliderSteps = sortedKeys.map(k => {{
    const fd = monthlyData[k];
    return {{
      args:[[k],{{frame:{{duration:250,redraw:true}},mode:"immediate",transition:{{duration:80}}}}],
      label: fd.month===1 ? String(fd.year) : "",
      method:"animate",
    }};
  }});

  // ── Show UI ────────────────────────────────────────────────────────────────
  buildBasinSelector();
  buildDateDropdowns();
  document.getElementById("loading").style.display = "none";
  document.getElementById("content").style.display  = "block";

  const fd0 = monthlyData[sortedKeys[0]];
  await Plotly.newPlot(
    "mapDiv",
    [makeTrace(fd0.vals)],
    makeTrackerLayout(fd0, cachedSliderSteps),
    {{responsive:true}}
  );
  await Plotly.addFrames("mapDiv", buildFrames());

  renderTimeSeries(currentBasin);
  renderClimatology(currentBasin);
}}

init().catch(err => {{
  document.getElementById("loading").innerHTML =
    "<p style='color:var(--muted)'>Error: "+err.message+"</p>";
}});
</script>
</body>
</html>
"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html, encoding="utf-8")
    size_kb = Path(output_path).stat().st_size // 1024
    print(f"SST page written → {output_path}  ({size_kb} KB)")


if __name__ == "__main__":
    render_sst()
