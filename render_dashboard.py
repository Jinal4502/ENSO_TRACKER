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

    # chart data
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

    # Gauge needle angle: maps -3..+3 anomaly → -90°..+90°
    needle_deg = max(-90, min(90, anom / 3.0 * 90))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ENSO Tracker — {fetched}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
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
  /* Footer */
  footer {{ font-size: 0.75rem; color: var(--muted); margin-top: 1.5rem; text-align: center; }}
  footer a {{ color: var(--muted); }}
</style>
</head>
<body>

<h1>ENSO Tracker</h1>
<p class="subtitle">Updated {fetched} · Source: NOAA/CPC</p>

<div class="grid">
  <!-- Current State -->
  <div class="card">
    <h2>Current State</h2>
    <span class="badge">{status_badge}</span>
    <div class="big-num">{anom:+.2f} °C</div>
    <div class="label">{label}</div>
    <div class="row" style="margin-top:.6rem">
      <span>Niño-3.4 SST anomaly (weekly)</span>
    </div>
  </div>

  <!-- Gauge -->
  <div class="card">
    <h2>Anomaly Gauge</h2>
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
    <h2>CPC Advisory</h2>
    {f'<p style="font-size:.78rem;color:var(--muted);margin-bottom:.5rem">Issued: {issued}</p>' if issued else ''}
    <p class="synopsis">{synopsis or "Diagnostic Discussion not yet available for this week."}</p>
  </div>
</div>

<!-- Weekly anomaly chart -->
<div class="chart-card">
  <h2>Niño-3.4 Weekly Anomaly — Last 52 Weeks</h2>
  <canvas id="weeklyChart"></canvas>
</div>

<!-- ONI vs RONI chart -->
<div class="chart-card">
  <h2>ONI vs RONI — Last 3 Years (Monthly)</h2>
  <canvas id="oniChart"></canvas>
</div>

<!-- Impacts -->
<div class="card impacts" style="margin-bottom:1rem">
  <h2>Regional Impacts — {label}</h2>
  <ul>{impact_li}</ul>
</div>

<footer>
  Data: NOAA/CPC
</footer>

<script>
const chartDefaults = {{
  plugins: {{ legend: {{ labels: {{ color: '#8b949e', font: {{ size: 11 }} }} }} }},
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
    with open(data_path) as f:
        data = json.load(f)
    render(data)
