"""
render_precipitation.py
Generates docs/precipitation.html — Southwest US precipitation dashboard.
sw_monthly_grid.csv is loaded at browser runtime; no server-side data processing.
"""

from pathlib import Path


def render_precipitation(meta: dict, output_path: str = "docs/precipitation.html") -> None:
    if not meta:
        print("[WARN] No precipitation metadata — skipping render")
        return

    first  = meta.get("first_month", "1970-01")
    last   = meta.get("last_month",  "2026-06")
    states = sorted(meta.get("states", ["AZ", "CA", "CO", "NM", "NV", "TX", "UT"]))
    yr0    = first[:4]
    yr1    = last[:4]

    state_buttons = "\n".join(
        f'      <button class="btn" data-state="{s}">{s}</button>'
        for s in states
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Southwest US Precipitation Tracker</title>
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
  footer {{ font-size:.75rem; color:var(--muted); margin-top:1.5rem; text-align:center; }}
  footer a {{ color:var(--muted); }}
</style>
</head>
<body>

<nav class="topnav">
  <a class="nav-brand" href="index.html">ENSO Tracker</a>
  <div class="nav-links">
    <a href="index.html">ENSO Dashboard</a>
    <a href="hurricanes.html">Cyclone Tracker</a>
    <a href="precipitation.html" class="nav-active">SW Precipitation</a>
  </div>
</nav>

<h1>Southwest US Precipitation</h1>
<p class="subtitle">
  NClimGrid monthly total &middot; {yr0}&ndash;{yr1} &middot; 0.5&deg; Gaussian-smoothed grid &middot;
  Source: <a href="https://www.ncei.noaa.gov/products/land-based-station/nclimgrid-monthly"
             target="_blank">NOAA/NCEI NClimGrid</a>
</p>

<div id="loading" style="text-align:center;padding:3rem;color:var(--muted)">
  Loading precipitation data&hellip;
</div>

<div id="content">

  <!-- Map -->
  <div class="card">
    <h2>Precipitation Composite Map &mdash; Southwest US</h2>
    <p style="font-size:.78rem;color:var(--muted);margin-bottom:.6rem">
      Gaussian-smoothed 0.5&deg; grid. Toggle ENSO phase to compare spatial precipitation
      patterns across El Ni&ntilde;o, La Ni&ntilde;a, and Neutral years.
    </p>
    <div class="btn-row" id="ensoToggle">
      <button class="btn active" data-enso="all">All Years</button>
      <button class="btn" data-enso="El Niño">El Ni&ntilde;o</button>
      <button class="btn" data-enso="La Niña">La Ni&ntilde;a</button>
      <button class="btn" data-enso="Neutral">Neutral</button>
    </div>
    <div id="mapDiv" style="height:520px;width:100%"></div>
  </div>

  <!-- State selector -->
  <div class="card">
    <h2>Select State</h2>
    <p style="font-size:.78rem;color:var(--muted);margin-bottom:.6rem">
      Click a state to update the time series and climatology charts below.
    </p>
    <div class="btn-row" id="stateSelector">
      <button class="btn active" data-state="all">All SW</button>
{state_buttons}
    </div>
  </div>

  <!-- Time series -->
  <div class="card">
    <h2 id="lineTitle">Monthly Precipitation &mdash; All SW ({yr0}&ndash;{yr1})</h2>
    <p style="font-size:.78rem;color:var(--muted);margin-bottom:.5rem">
      Area-average monthly precipitation.
      <span style="background:rgba(239,83,80,.22);padding:1px 5px;border-radius:3px">El Ni&ntilde;o</span>
      and
      <span style="background:rgba(30,136,229,.22);padding:1px 5px;border-radius:3px">La Ni&ntilde;a</span>
      periods shaded per NOAA 5-season rule.
    </p>
    <div id="lineDiv"></div>
  </div>

  <!-- Climatology by ENSO phase -->
  <div class="card">
    <h2 id="climTitle">Monthly Climatology &mdash; All SW by ENSO Phase</h2>
    <p style="font-size:.78rem;color:var(--muted);margin-bottom:.5rem">
      Long-term average precipitation for each calendar month, split by ENSO phase.
      Reveals the seasonal fingerprint of El Ni&ntilde;o and La Ni&ntilde;a on regional rainfall.
    </p>
    <div id="climDiv"></div>
  </div>

</div>

<footer>
  Data: <a href="https://www.ncei.noaa.gov/products/land-based-station/nclimgrid-monthly"
           target="_blank">NOAA/NCEI NClimGrid</a> &middot;
  ENSO: <a href="https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
           target="_blank">NOAA/CPC ONI</a>
  &nbsp;&middot;&nbsp;
  <a href="hurricanes.html">&#127744; Cyclone Tracker &rarr;</a>
</footer>

<script>
const MONTH_NAMES  = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const YR0 = "{yr0}", YR1 = "{yr1}";
const DARK = {{
  paper:"#0d1117", plot:"#0d1117", text:"#c9d1d9",
  muted:"#8b949e", grid:"#21262d", card:"#1c2128", border:"#30363d"
}};
const PRCP_SCALE = [
  [0.00,"#0d1117"],[0.05,"#1a0500"],[0.15,"#6b0000"],
  [0.30,"#b91c00"],[0.48,"#e85d00"],[0.65,"#f5a623"],
  [0.80,"#fcd53a"],[0.92,"#fff176"],[1.00,"#fffde7"]
];
const ENSO_PHASES  = ["El Niño","Neutral","La Niña"];
const ENSO_COLORS  = ["#ef5350","#8b949e","#1e88e5"];
const ENSO_FILL    = {{"El Niño":"rgba(239,83,80,0.18)","La Niña":"rgba(30,136,229,0.18)"}};

// Populated in init()
let composites = {{}};  // phase → {{lats, lons, vals}}   (for map)
let stateRows  = {{}};  // state → [rows]                 (for charts)
let cmapMax    = 100;   // 95th-pct colorscale cap

// ── CSV parser ───────────────────────────────────────────────────────────────
function parseCSV(text) {{
  const lines = text.trim().split(/\\r?\\n/);
  const keys  = lines[0].split(",").map(k => k.trim());
  return lines.slice(1).filter(l => l.trim()).map(l => {{
    const v = l.split(",");
    return Object.fromEntries(keys.map((k,i) => [k, (v[i]||"").trim()]));
  }});
}}

// ── Cell-level average: collapse (year,month) → one value per (lat,lon) ─────
function cellAvg(rows) {{
  const S = {{}}, N = {{}};
  for (const r of rows) {{
    const k = r.lat + "," + r.lon;
    S[k] = (S[k]||0) + +r.prcp_mm;
    N[k] = (N[k]||0) + 1;
  }}
  const lats=[], lons=[], vals=[];
  for (const k of Object.keys(S)) {{
    const [la,lo] = k.split(",").map(Number);
    lats.push(la); lons.push(lo);
    vals.push(+(S[k]/N[k]).toFixed(1));
  }}
  return {{lats, lons, vals}};
}}

// ── Map ──────────────────────────────────────────────────────────────────────
function renderMap(phase) {{
  const {{lats, lons, vals}} = composites[phase] || composites["all"];
  const label = phase === "all" ? "All Years" : phase;
  Plotly.react("mapDiv", [{{
    type: "scattermapbox", mode: "markers",
    lat: lats, lon: lons,
    marker: {{
      size: 18, opacity: 0.9,
      color: vals, colorscale: PRCP_SCALE, cmin: 0, cmax: cmapMax,
      colorbar: {{
        title: {{text:"mm/month", font:{{color:DARK.text,size:10}}}},
        tickfont: {{color:DARK.text, size:10}},
        bgcolor: "rgba(22,27,34,0.85)", bordercolor:DARK.border, borderwidth:1,
        len:0.55, thickness:14, x:1.01, xpad:8
      }}
    }},
    hovertemplate: "<b>%{{lat:.2f}}°N, %{{lon:.2f}}°E</b><br>%{{marker.color:.1f}} mm/mo avg<extra></extra>",
    showlegend: false
  }}], {{
    autosize: true,
    paper_bgcolor: DARK.paper,
    mapbox: {{style:"carto-darkmatter", center:{{lat:35.5,lon:-109}}, zoom:3.4}},
    margin: {{l:0, r:65, t:0, b:20}},
    annotations: [{{
      text: label,
      x:0.01, y:0.97, xref:"paper", yref:"paper",
      xanchor:"left", yanchor:"top", showarrow:false,
      font:{{size:16, color:"#e6edf3", family:"monospace", weight:700}},
      bgcolor:"rgba(13,17,23,0.75)", borderpad:4
    }}]
  }}, {{responsive:true}});
}}

// ── Time series ───────────────────────────────────────────────────────────────
function renderTimeSeries(stateKey) {{
  const rows = stateRows[stateKey] || [];
  // Average across all cells per (year, month)
  const mdata = {{}};
  for (const r of rows) {{
    const k = r.year + "-" + r.month.padStart(2,"0");
    if (!mdata[k]) mdata[k] = {{sum:0, cnt:0, enso:r.enso, year:+r.year, month:+r.month}};
    mdata[k].sum += +r.prcp_mm;
    mdata[k].cnt++;
  }}
  const keys  = Object.keys(mdata).sort();
  const msX   = keys.map(k => {{ const d=mdata[k]; return d.year+"-"+String(d.month).padStart(2,"0")+"-01"; }});
  const msY   = keys.map(k => +(mdata[k].sum/mdata[k].cnt).toFixed(2));
  const msENSO= keys.map(k => mdata[k].enso);

  // Build background ENSO shading shapes
  const shapes = [];
  for (let si=0; si<msX.length;) {{
    let ei = si;
    while (ei+1 < msX.length && msENSO[ei+1] === msENSO[si]) ei++;
    if (ENSO_FILL[msENSO[si]]) {{
      const x1 = ei+1 < msX.length ? msX[ei+1]
        : new Date(new Date(msX[ei]).setMonth(new Date(msX[ei]).getMonth()+1))
            .toISOString().slice(0,10);
      shapes.push({{type:"rect",layer:"below",xref:"x",yref:"paper",
        x0:msX[si], x1, y0:0, y1:1,
        fillcolor:ENSO_FILL[msENSO[si]], line:{{width:0}}}});
    }}
    si = ei+1;
  }}

  const label = stateKey==="all" ? "All SW" : stateKey;
  document.getElementById("lineTitle").textContent =
    "Monthly Precipitation — " + label + " (" + YR0 + "–" + YR1 + ")";

  Plotly.react("lineDiv", [
    {{type:"scatter", mode:"lines", x:msX, y:msY,
      line:{{color:"#f5a623", width:1.5}},
      fill:"tozeroy", fillcolor:"rgba(245,166,35,0.07)",
      customdata:msENSO,
      hovertemplate:"<b>%{{x|%b %Y}}</b><br>%{{y:.1f}} mm<br>%{{customdata}}<extra></extra>",
      showlegend:false}},
    {{type:"scatter",x:[null],y:[null],mode:"markers",name:"El Niño",
      marker:{{color:"rgba(239,83,80,0.7)",symbol:"square",size:11}},showlegend:true}},
    {{type:"scatter",x:[null],y:[null],mode:"markers",name:"La Niña",
      marker:{{color:"rgba(30,136,229,0.7)",symbol:"square",size:11}},showlegend:true}},
    {{type:"scatter",x:[null],y:[null],mode:"markers",name:"Neutral",
      marker:{{color:"rgba(139,148,158,0.5)",symbol:"square",size:11}},showlegend:true}},
  ], {{
    autosize:true, paper_bgcolor:DARK.paper, plot_bgcolor:DARK.paper, height:280,
    margin:{{l:55,r:20,t:15,b:40}}, shapes,
    xaxis:{{type:"date",dtick:"M60",tickformat:"%Y",color:DARK.muted,gridcolor:DARK.grid}},
    yaxis:{{title:"mm / month",rangemode:"tozero",color:DARK.muted,gridcolor:DARK.grid}},
    legend:{{x:0.01,y:0.99,font:{{color:DARK.text,size:11}},
             bgcolor:DARK.card,bordercolor:DARK.border,borderwidth:1}}
  }}, {{responsive:true}});
}}

// ── Climatology by ENSO phase ─────────────────────────────────────────────────
function renderClimatology(stateKey) {{
  const rows = stateRows[stateKey] || [];
  // Accumulate per (ENSO phase, month-index) — average across cells and years
  const byPhase = {{}};
  for (const ph of ENSO_PHASES)
    byPhase[ph] = Array.from({{length:12}}, () => ({{s:0, n:0}}));
  for (const r of rows) {{
    const ph = r.enso;
    if (!byPhase[ph]) continue;
    byPhase[ph][+r.month-1].s += +r.prcp_mm;
    byPhase[ph][+r.month-1].n++;
  }}

  const label = stateKey==="all" ? "All SW" : stateKey;
  document.getElementById("climTitle").textContent =
    "Monthly Climatology — " + label + " by ENSO Phase";

  Plotly.react("climDiv",
    ENSO_PHASES.map((ph,i) => ({{
      type:"bar", name:ph, x:MONTH_NAMES,
      y: byPhase[ph].map(d => d.n ? +(d.s/d.n).toFixed(1) : 0),
      marker:{{color:ENSO_COLORS[i], opacity:0.85}},
      hovertemplate:"<b>%{{x}} — "+ph+"</b><br>%{{y:.1f}} mm avg<extra></extra>"
    }})),
  {{
    autosize:true, barmode:"group",
    paper_bgcolor:DARK.paper, plot_bgcolor:DARK.paper, height:260,
    margin:{{l:50,r:20,t:10,b:40}},
    xaxis:{{color:DARK.muted, gridcolor:DARK.grid}},
    yaxis:{{title:"mm", color:DARK.muted, gridcolor:DARK.grid}},
    legend:{{font:{{color:DARK.text,size:11}},
             bgcolor:DARK.card,bordercolor:DARK.border,borderwidth:1}}
  }}, {{responsive:true}});
}}

// ── Button event handlers ─────────────────────────────────────────────────────
document.getElementById("ensoToggle").addEventListener("click", e => {{
  const btn = e.target.closest("[data-enso]");
  if (!btn) return;
  document.querySelectorAll("#ensoToggle .btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  renderMap(btn.dataset.enso);
}});

document.getElementById("stateSelector").addEventListener("click", e => {{
  const btn = e.target.closest("[data-state]");
  if (!btn) return;
  document.querySelectorAll("#stateSelector .btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  const s = btn.dataset.state;
  renderTimeSeries(s);
  renderClimatology(s);
}});

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {{
  const text = await fetch("data/sw_monthly_grid.csv").then(r => r.text());
  const rows = parseCSV(text);

  // Pre-group by state for O(1) filtering on every button click
  stateRows["all"] = rows;
  for (const r of rows) {{
    if (!stateRows[r.state]) stateRows[r.state] = [];
    stateRows[r.state].push(r);
  }}

  // Pre-compute ENSO composite maps (cell averages per ENSO phase)
  for (const ph of ["all", ...ENSO_PHASES]) {{
    const sub = ph === "all" ? rows : rows.filter(r => r.enso === ph);
    composites[ph] = cellAvg(sub);
  }}

  // 95th-percentile cap for the map colorscale
  const sorted = [...composites["all"].vals].sort((a,b) => a-b);
  cmapMax = Math.round(sorted[Math.floor(sorted.length * 0.95)] / 10) * 10 || 100;

  document.getElementById("loading").style.display = "none";
  document.getElementById("content").style.display  = "block";

  renderMap("all");
  renderTimeSeries("all");
  renderClimatology("all");
}}

init().catch(err => {{
  document.getElementById("loading").textContent = "Error loading data: " + err.message;
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
