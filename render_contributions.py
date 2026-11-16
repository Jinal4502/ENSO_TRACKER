#!/usr/bin/env python3
"""
render_contributions.py — El Niño 2026-27 Global Contributions Map

Reads El Niño 2026-27 Contributions (responses).xlsx, applies hardcoded
geocoordinates, cleans data, and writes docs/contributions.html.

Excludes responses with "No (research use only)" permission.
Anonymous entries display contributor name/affil as "Anonymous Contributor".

Re-run after updating the spreadsheet; not wired into the weekly CI
(survey data is static between update rounds).
"""
import json
import re
from pathlib import Path
import openpyxl

XLSX_PATH = "El Niño 2026-27 Contributions (responses).xlsx"
OUT_PATH  = "docs/contributions.html"

# ---------------------------------------------------------------------------
# Hardcoded geocoordinates (row index 1-based, matching xlsx data rows)
# ---------------------------------------------------------------------------
COORDS = {
    1:  (-0.18,  -78.47),   # Ecuador – Quito
    2:  (-1.00,  -79.50),   # Ecuador – ENSO influence zone (offset from row 1)
    3:  (37.57,  127.00),   # South Korea – Seoul
    4:  (50.00,  -84.50),   # Canada – Northern Ontario
    5:  (23.79,   86.43),   # India – Dhanbad
    6:  (25.28,   51.52),   # Qatar – Middle East
    7:  (-2.50,   37.80),   # Kenya – Lower Makueni
    8:  (17.50,  121.50),   # Philippines – Northern Luzon
    9:  (25.10,   85.30),   # India – Bihar
    10: (23.03,   72.59),   # India – Ahmedabad/urban (heatwave context)
    11: (-7.50,  112.50),   # Indonesia – East Java
    12: (24.00,   76.00),   # India – unspecified (center)
    13: (-8.60,  116.30),   # Indonesia – West Nusa Tenggara (NTB)
    14: (13.50,   38.00),   # Ethiopia – Tekeze Basin
    15: (-3.50,  104.50),   # Indonesia – South Sumatra
    16: (-9.40,  124.90),   # Indonesia – Timor Island, East Nusa Tenggara
    17: (-4.50,  120.30),   # Indonesia – South Sulawesi (Bone & Wajo)
    18: (-8.65,  115.20),   # Indonesia – Bali
    19: (-1.68,  113.40),   # Indonesia – Central Kalimantan
    20: (-8.47,  140.40),   # Indonesia – Merauke, South Papua
    21: (-1.00,   40.00),   # Kenya – Lower Tana River Basin (offset from row 7)
    22: (-5.19,  -80.63),   # Peru – Piura
    23: (-17.00,  28.80),   # Zambia – Lake Kariba
    24: (-27.50, 152.50),   # Australia – SE Queensland
    25: (-6.10,  107.10),   # Indonesia – West Java (Karawang)
    26: (36.80,    9.50),   # Tunisia
    27: (31.63,   74.87),   # India – Amritsar, Punjab
    28: (22.30,  114.20),   # Hong Kong
    29: (28.47,   77.03),   # India – Gurugram
    30: (12.30,   76.65),   # India – Cauvery River Basin
    31: (-34.00, -71.00),   # Chile – Central Chile
    32: (-33.45, -70.67),   # Chile – Santiago (offset from row 31)
    33: (-1.94,   29.87),   # Rwanda
    34: (-25.00, -57.50),   # Paraguay – Cuenca del río Paraná
    35: (6.00,    37.00),   # Ethiopia – Gamo Highlands (offset from row 14)
    36: (-28.30, -49.90),   # Brazil – São Joaquim, SC
    37: (31.96,   77.11),   # India – Kullu, Himachal Pradesh
    38: (36.20,  138.30),   # Japan
    39: (51.50,   -0.10),   # United Kingdom
    # Row 40 (Nepal): "No (research use only)" – excluded
    41: (34.00, -112.00),   # USA – Southwest
}

HAZARD_KEY = {
    "Multiple or general":     "multiple",
    "Drought":                 "drought",
    "Riverine flood":          "flood",
    "Flash flood":             "flash",
    "Above-normal rainfall":   "rain_hi",
    "Below-normal rainfall":   "rain_lo",
    "Heatwave":                "heat",
    "Wildfire":                "fire",
}

SEV_LABEL = {1: "Minor", 2: "Low", 3: "Moderate", 4: "High", 5: "Extreme"}

WHAT_LABEL = {
    "An impact already observed":              "Observed impact",
    "Expert analysis or recommendation":       "Expert analysis",
    "An expected impact or outlook":           "Expected / Outlook",
    "Data or research I want to contribute":   "Research contribution",
}

# Observations that are administrative/junk (exact match after lower+strip)
_JUNK_OBS = {"observed", "no number", "na", "nil", "none", "n/a"}


def _clean_name(name: str) -> str:
    if not name:
        return name
    n = name.strip()
    words = n.split()
    alpha_words = [w for w in words if any(c.isalpha() for c in w)]
    if alpha_words and all(w == w.upper() for w in alpha_words):
        # All-caps: use regex title-case that respects non-alpha word boundaries
        return re.sub(r'\b\w', lambda m: m.group().upper(), n.lower())
    if n == n.lower():
        return n.title()
    return n


def _clean_obs(text) -> str:
    if not text:
        return ""
    t = str(text).strip()
    if t.lower() in _JUNK_OBS:
        return ""
    return t


def _clean_links(raw) -> list:
    if not raw:
        return []
    urls = re.findall(r'https?://[^\s\n]+', str(raw))
    return [u.rstrip('.,)') for u in urls][:5]


def _sectors(raw) -> list:
    if not raw:
        return []
    return [s.strip() for s in str(raw).split(",") if s.strip()]


def load_entries() -> list:
    wb = openpyxl.load_workbook(XLSX_PATH)
    ws = wb.active
    entries = []
    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 1):
        (ts, email, name, affil, role, field, permission, what,
         country, place, hazard, sectors, severity, when, obs, links,
         share_data, extra) = row

        if permission and "research use only" in str(permission).lower():
            continue
        if idx not in COORDS:
            continue

        lat, lon  = COORDS[idx]
        anon      = "anonymously" in str(permission or "").lower()
        haz       = str(hazard or "Multiple or general").strip()
        sev       = int(severity) if severity else None

        entry = {
            "id":        idx,
            "lat":       lat,
            "lon":       lon,
            "country":   str(country or "").strip(),
            "place":     str(place or "").strip(),
            "hazard":    haz,
            "hkey":      HAZARD_KEY.get(haz, "multiple"),
            "severity":  sev,
            "sev_label": SEV_LABEL.get(sev, "") if sev else "",
            "what":      WHAT_LABEL.get(str(what or "").strip(), str(what or "").strip()),
            "sectors":   _sectors(sectors),
            "when":      str(when or "").strip(),
            "obs":       _clean_obs(obs),
            "links":     _clean_links(links),
            "name":      None if anon else _clean_name(name),
            "role":      None if anon else str(role or "").strip(),
            "affil":     None if anon else str(affil or "").strip(),
            "anon":      anon,
        }
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# HTML template — split into three parts to avoid f-string brace-escaping the
# large JS section. Only the middle part uses Python substitution.
# ---------------------------------------------------------------------------

_HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>El Niño Contributions · ENSO Tracker</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<style>
  :root {
    --accent: hsl(265,75%,62%);
    --bg: #0d1117;
    --card: #161b22;
    --border: #30363d;
    --text: #c9d1d9;
    --muted: #8b949e;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text);
    font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
    padding: 1.5rem; }
  /* Nav */
  .topnav { display:flex; align-items:center; justify-content:space-between;
    padding:.5rem 0; border-bottom:1px solid var(--border); margin-bottom:1.2rem; }
  .nav-brand { font-weight:700; font-size:.95rem; color:var(--text); text-decoration:none; }
  .nav-links { display:flex; gap:.4rem; flex-wrap:wrap; }
  .nav-links a { color:var(--muted); text-decoration:none; font-size:.82rem;
    padding:.3rem .7rem; border-radius:5px; }
  .nav-links a:hover { color:var(--text); background:var(--card); }
  .nav-links a.nav-active { color:#fff; background:var(--accent); font-weight:600; }
  /* Header */
  h1 { font-size:1.4rem; font-weight:700; margin-bottom:.2rem; }
  .subtitle { color:var(--muted); font-size:.85rem; margin-bottom:1.2rem; }
  /* Stats */
  .stats { display:flex; gap:2rem; margin-bottom:1rem; flex-wrap:wrap; }
  .stat { display:flex; flex-direction:column; }
  .stat-num { font-size:1.6rem; font-weight:700; color:var(--accent); line-height:1; }
  .stat-label { font-size:.7rem; color:var(--muted); text-transform:uppercase;
    letter-spacing:.06em; margin-top:.18rem; }
  /* Filters */
  .filters { display:flex; gap:.4rem; flex-wrap:wrap; margin-bottom:.85rem; align-items:center; }
  .filters-label { font-size:.72rem; color:var(--muted); text-transform:uppercase;
    letter-spacing:.05em; margin-right:.2rem; }
  .filter-btn { background:var(--card); border:1px solid var(--border); color:var(--muted);
    font-size:.78rem; padding:.3rem .75rem; border-radius:20px; cursor:pointer;
    transition:all .15s; white-space:nowrap; }
  .filter-btn:hover { color:var(--text); }
  .filter-btn.active { color:#fff !important; font-weight:600; }
  /* Map */
  .map-wrap { border-radius:10px; overflow:hidden; border:1px solid var(--border);
    margin-bottom:.85rem; }
  #map { height:72vh; min-height:420px; width:100%; background:#0d1117; }
  /* Legend */
  .legend { display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:1.6rem;
    padding:.6rem .8rem; background:var(--card); border:1px solid var(--border);
    border-radius:8px; align-items:center; }
  .legend-title { font-size:.7rem; color:var(--muted); text-transform:uppercase;
    letter-spacing:.05em; margin-right:.3rem; }
  .leg-item { display:flex; align-items:center; gap:.35rem; font-size:.75rem;
    color:var(--muted); cursor:pointer; padding:.15rem .3rem; border-radius:4px;
    transition:.12s; }
  .leg-item:hover { color:var(--text); background:rgba(255,255,255,.04); }
  .leg-dot { width:11px; height:11px; border-radius:50%; border:1.5px solid rgba(255,255,255,.25);
    flex-shrink:0; }
  .leg-sev { font-size:.7rem; color:var(--muted); margin-left:.8rem;
    padding-left:.8rem; border-left:1px solid var(--border); }
  /* Popup */
  .leaflet-popup-content-wrapper {
    background:#1c2130;
    border:1px solid #2d3550;
    border-radius:10px;
    box-shadow:0 12px 40px rgba(0,0,0,.8), 0 0 0 1px rgba(255,255,255,.04);
    padding:0;
    max-width:380px;
    overflow:hidden;
  }
  .leaflet-popup-content { margin:0 !important; width:100% !important; }
  .leaflet-popup-tip-container { margin-top:-1px; }
  .leaflet-popup-tip { background:#1c2130; }
  .leaflet-popup-close-button {
    color:#8b949e !important; top:9px !important; right:11px !important;
    font-size:17px !important; font-weight:400 !important; z-index:10;
  }
  .leaflet-popup-close-button:hover { color:#e6edf3 !important; }
  /* Popup card */
  .pcard { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
    color:#c9d1d9; }
  .pcard-head { padding:.75rem 2.2rem .6rem 1rem; border-bottom:1px solid #2d3550;
    display:flex; justify-content:space-between; align-items:center; gap:.6rem;
    flex-wrap:wrap; }
  .phazard-badge { font-size:.7rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.06em; padding:.22rem .6rem; border-radius:4px; white-space:nowrap; }
  .psev-row { display:flex; align-items:center; gap:.35rem; }
  .psev-dot { width:7px; height:7px; border-radius:50%; background:#2d3550; flex-shrink:0; }
  .psev-dot.on { background:currentColor; }
  .psev-text { font-size:.68rem; color:#8b949e; white-space:nowrap; }
  .pcard-loc { padding:.45rem 1rem; font-size:.82rem; color:#8b949e;
    border-bottom:1px solid #2d3550; display:flex; align-items:baseline; gap:.4rem;
    flex-wrap:wrap; }
  .pcard-loc strong { color:#c9d1d9; }
  .pcard-loc .pwhen { font-size:.72rem; color:#6e7681; }
  .pcard-who { padding:.5rem 1rem; border-bottom:1px solid #2d3550; }
  .pcard-who .pname { font-size:.88rem; font-weight:600; color:#e6edf3; }
  .pcard-who .pmeta { font-size:.74rem; color:#8b949e; margin-top:.15rem; line-height:1.4; }
  .pcard-what { padding:.38rem 1rem; border-bottom:1px solid #2d3550;
    font-size:.72rem; color:#8b949e; }
  .pcard-what em { font-style:normal; color:#a78bfa; }
  .pcard-tags { padding:.5rem 1rem; border-bottom:1px solid #2d3550;
    display:flex; flex-wrap:wrap; gap:.3rem; }
  .ptag { font-size:.67rem; padding:.15rem .4rem; border-radius:3px;
    background:#21262d; color:#8b949e; border:1px solid #2d3550; }
  .pcard-obs { padding:.6rem 1rem; font-size:.8rem; line-height:1.6; color:#c9d1d9;
    border-bottom:1px solid #2d3550; max-height:170px; overflow-y:auto;
    white-space:pre-wrap; }
  .pcard-obs::-webkit-scrollbar { width:4px; }
  .pcard-obs::-webkit-scrollbar-track { background:transparent; }
  .pcard-obs::-webkit-scrollbar-thumb { background:#30363d; border-radius:2px; }
  .pcard-links { padding:.5rem 1rem; display:flex; flex-wrap:wrap; gap:.4rem; }
  .plink { font-size:.72rem; color:#58a6ff; text-decoration:none; white-space:nowrap;
    overflow:hidden; text-overflow:ellipsis; max-width:320px; display:inline-block; }
  .plink:hover { text-decoration:underline; }
  /* Cluster */
  .marker-cluster-small,
  .marker-cluster-medium,
  .marker-cluster-large { background:transparent !important; }
  .marker-cluster-small div,
  .marker-cluster-medium div,
  .marker-cluster-large div {
    background:rgba(168,85,247,.75) !important;
    color:#fff !important; font-weight:700; font-size:.78rem;
    border:2px solid rgba(255,255,255,.35) !important;
  }
  /* Severity legend circles */
  .leg-sev-row { display:flex; align-items:center; gap:.5rem; }
  .sev-circle { border-radius:50%; border:1.5px solid rgba(255,255,255,.3);
    background:#a855f7; display:inline-block; flex-shrink:0; }
  @media (max-width:600px) {
    body { padding:1rem; }
    .stats { gap:1.2rem; }
    #map { height:60vh; }
  }
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
    <a href="sst.html">Sea Surface Temp</a>
    <a href="impacts.html">Impacts</a>
    <a href="facts.html">Quick Facts</a>
    <a href="research.html">Research</a>
    <a href="contributions.html" class="nav-active">Contributions</a>
  </div>
</nav>
<h1>El Niño 2026-27 · Global Impact Contributions</h1>
<p class="subtitle">Observations, analyses, and outlooks submitted by researchers and practitioners worldwide. Click any marker to explore.</p>
"""

_TAIL = """\
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
(function () {
  const COLORS = {
    multiple: "#a855f7",
    drought:  "#f97316",
    flood:    "#3b82f6",
    flash:    "#06b6d4",
    rain_hi:  "#60a5fa",
    rain_lo:  "#fbbf24",
    heat:     "#ef4444",
    fire:     "#c2410c",
  };
  const HLABELS = {
    multiple: "Multiple / General",
    drought:  "Drought",
    flood:    "Riverine Flood",
    flash:    "Flash Flood",
    rain_hi:  "Above-normal Rainfall",
    rain_lo:  "Below-normal Rainfall",
    heat:     "Heatwave",
    fire:     "Wildfire",
  };
  const SEV = {1:"Minor",2:"Low",3:"Moderate",4:"High",5:"Extreme"};

  // Map
  const map = L.map("map", {
    center: [15, 10], zoom: 2, minZoom: 1, maxZoom: 10, worldCopyJump: true,
  });
  // Esri Dark Gray Canvas — no API key required
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
    attribution: 'Tiles &copy; <a href="https://www.esri.com/" style="color:#58a6ff">Esri</a> &mdash; Esri, DeLorme, NAVTEQ',
    maxZoom: 16,
  }).addTo(map);
  // Reference layer (labels)
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}", {
    attribution: "",
    maxZoom: 16,
    pane: "overlayPane",
  }).addTo(map);

  function makeIcon(hkey, sev) {
    const col = COLORS[hkey] || "#a855f7";
    const s   = sev || 2;
    const r   = 7 + s * 2.5;
    const d   = r * 2;
    const glow = s >= 4 ? `box-shadow:0 0 ${s * 4}px ${col}99` : `box-shadow:0 0 ${s * 2}px ${col}66`;
    return L.divIcon({
      html: `<div style="width:${d}px;height:${d}px;border-radius:50%;background:${col};border:2px solid rgba(255,255,255,.65);${glow};opacity:.92;cursor:pointer"></div>`,
      className: "", iconSize: [d, d], iconAnchor: [r, r], popupAnchor: [0, -r - 4],
    });
  }

  function sevDots(sev, col) {
    if (!sev) return "";
    let h = `<div class="psev-row" style="color:${col}">`;
    for (let i = 1; i <= 5; i++) h += `<div class="psev-dot${i <= sev ? " on" : ""}"></div>`;
    h += `<span class="psev-text">${SEV[sev] || sev}</span></div>`;
    return h;
  }

  function esc(s) {
    return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }

  function makePopup(d) {
    const col    = COLORS[d.hkey] || "#a855f7";
    const hLabel = HLABELS[d.hkey] || d.hazard;
    const loc    = d.place ? `${d.place}, ${d.country}` : d.country;

    let whoHtml = "";
    if (d.anon) {
      whoHtml = `<div class="pcard-who"><div class="pname">Anonymous Contributor</div></div>`;
    } else if (d.name) {
      const parts = [d.role, d.affil].filter(Boolean).join(" &middot; ");
      whoHtml = `<div class="pcard-who">
        <div class="pname">${esc(d.name)}</div>
        ${parts ? `<div class="pmeta">${esc(parts)}</div>` : ""}
      </div>`;
    }

    const tags = (d.sectors || []).map(s =>
      `<span class="ptag">${esc(s)}</span>`).join("");
    const tagsHtml = tags
      ? `<div class="pcard-tags">${tags}</div>` : "";

    const obsHtml = d.obs
      ? `<div class="pcard-obs">${esc(d.obs)}</div>` : "";

    const linksHtml = d.links && d.links.length
      ? `<div class="pcard-links">${d.links.map(u => {
          let label;
          try { label = new URL(u).hostname.replace("www.", ""); } catch(e) { label = "Link"; }
          return `<a href="${u}" target="_blank" rel="noopener" class="plink">&#8599; ${esc(label)}</a>`;
        }).join("")}</div>` : "";

    return `<div class="pcard">
      <div class="pcard-head">
        <span class="phazard-badge" style="background:${col}22;color:${col};border:1px solid ${col}55">${hLabel}</span>
        ${d.severity ? sevDots(d.severity, col) : ""}
      </div>
      <div class="pcard-loc">
        <strong>&#128205; ${esc(loc)}</strong>
        ${d.when ? `<span class="pwhen">&#183; Est. ${esc(d.when)}</span>` : ""}
      </div>
      ${whoHtml}
      ${d.what ? `<div class="pcard-what">Sharing: <em>${esc(d.what)}</em></div>` : ""}
      ${tagsHtml}
      ${obsHtml}
      ${linksHtml}
    </div>`;
  }

  // Build marker layer
  const mcg = L.markerClusterGroup({
    maxClusterRadius: 55,
    iconCreateFunction(cluster) {
      const c = cluster.getChildCount();
      const sz = c < 10 ? 36 : c < 20 ? 42 : 48;
      return L.divIcon({
        html: `<div style="width:${sz}px;height:${sz}px;border-radius:50%;background:rgba(168,85,247,.82);display:flex;align-items:center;justify-content:center;font-size:.8rem;font-weight:700;color:#fff;border:2px solid rgba(255,255,255,.4);box-shadow:0 0 14px rgba(168,85,247,.55)">${c}</div>`,
        className: "", iconSize: [sz, sz], iconAnchor: [sz / 2, sz / 2],
      });
    },
  });

  const allMarkers = DATA.map(d => {
    const m = L.marker([d.lat, d.lon], { icon: makeIcon(d.hkey, d.severity) });
    m.bindPopup(makePopup(d), { maxWidth: 380 });
    m._hkey = d.hkey;
    mcg.addLayer(m);
    return m;
  });
  mcg.addTo(map);

  // Filter logic
  let active = "all";
  const visEl = document.getElementById("vis-count");

  function applyFilter(hkey) {
    active = hkey;
    mcg.clearLayers();
    let count = 0;
    allMarkers.forEach(m => {
      if (hkey === "all" || m._hkey === hkey) { mcg.addLayer(m); count++; }
    });
    visEl.textContent = count;
  }

  document.querySelectorAll(".filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter-btn").forEach(b => {
        b.classList.remove("active");
        b.style.background  = "";
        b.style.borderColor = "";
        b.style.color       = "";
      });
      btn.classList.add("active");
      const c = btn.dataset.color;
      if (c) { btn.style.background = c + "33"; btn.style.borderColor = c + "88"; btn.style.color = "#fff"; }
      else { btn.style.background = "var(--accent)"; btn.style.color = "#fff"; btn.style.borderColor = "transparent"; }
      applyFilter(btn.dataset.hkey);
    });
  });

  // Legend click = filter
  document.querySelectorAll(".leg-item[data-hkey]").forEach(el => {
    el.addEventListener("click", () => {
      const btn = document.querySelector(`.filter-btn[data-hkey="${el.dataset.hkey}"]`);
      if (btn) btn.click();
    });
  });
})();
</script>
</body>
</html>
"""


def _filter_btn(hkey: str, label: str, color: str, active: bool = False) -> str:
    cls = ' class="filter-btn active"' if active else ' class="filter-btn"'
    style = ""
    if active:
        style = ' style="background:var(--accent);color:#fff;border-color:transparent"'
    return (f'<button{cls} data-hkey="{hkey}" data-color="{color}"{style}>'
            f'{label}</button>')


def render(entries: list) -> str:
    n        = len(entries)
    countries = len({e["country"] for e in entries})
    # Count by hazard for the stats dots
    haz_counts = {}
    for e in entries:
        haz_counts[e["hkey"]] = haz_counts.get(e["hkey"], 0) + 1

    data_js = json.dumps(entries, ensure_ascii=False, indent=2)

    mid = f"""\
<div class="stats">
  <div class="stat"><span class="stat-num">{n}</span><span class="stat-label">Contributions</span></div>
  <div class="stat"><span class="stat-num">{countries}</span><span class="stat-label">Countries</span></div>
  <div class="stat"><span class="stat-num" id="vis-count">{n}</span><span class="stat-label">Visible</span></div>
</div>

<div class="filters">
  <span class="filters-label">Filter:</span>
  {_filter_btn("all",      "All",             "",        active=True)}
  {_filter_btn("drought",  "Drought",         "#f97316")}
  {_filter_btn("flood",    "Riverine Flood",  "#3b82f6")}
  {_filter_btn("flash",    "Flash Flood",     "#06b6d4")}
  {_filter_btn("heat",     "Heatwave",        "#ef4444")}
  {_filter_btn("fire",     "Wildfire",        "#c2410c")}
  {_filter_btn("rain_hi",  "&#8593; Rainfall","#60a5fa")}
  {_filter_btn("rain_lo",  "&#8595; Rainfall","#fbbf24")}
  {_filter_btn("multiple", "Multiple",        "#a855f7")}
</div>

<div class="map-wrap">
  <div id="map"></div>
</div>

<div class="legend">
  <span class="legend-title">Hazard</span>
  <div class="leg-item" data-hkey="drought"><div class="leg-dot" style="background:#f97316"></div>Drought</div>
  <div class="leg-item" data-hkey="flood"><div class="leg-dot" style="background:#3b82f6"></div>Riverine Flood</div>
  <div class="leg-item" data-hkey="flash"><div class="leg-dot" style="background:#06b6d4"></div>Flash Flood</div>
  <div class="leg-item" data-hkey="heat"><div class="leg-dot" style="background:#ef4444"></div>Heatwave</div>
  <div class="leg-item" data-hkey="fire"><div class="leg-dot" style="background:#c2410c"></div>Wildfire</div>
  <div class="leg-item" data-hkey="rain_hi"><div class="leg-dot" style="background:#60a5fa"></div>&uarr; Rainfall</div>
  <div class="leg-item" data-hkey="rain_lo"><div class="leg-dot" style="background:#fbbf24"></div>&darr; Rainfall</div>
  <div class="leg-item" data-hkey="multiple"><div class="leg-dot" style="background:#a855f7"></div>Multiple</div>
  <span class="leg-sev">
    <div class="leg-sev-row">
      <div class="sev-circle" style="width:9px;height:9px"></div>
      <div class="sev-circle" style="width:14px;height:14px"></div>
      <div class="sev-circle" style="width:19px;height:19px"></div>
      <div class="sev-circle" style="width:24px;height:24px"></div>
      <div class="sev-circle" style="width:29px;height:29px"></div>
      <span style="font-size:.7rem;color:var(--muted);margin-left:.3rem">Minor → Extreme</span>
    </div>
  </span>
</div>

<script>const DATA = {data_js};</script>
"""
    return _HEAD + mid + _TAIL


def main():
    entries = load_entries()
    html = render(entries)
    Path(OUT_PATH).write_text(html, encoding="utf-8")
    n = len(entries)
    countries = len({e["country"] for e in entries})
    anon_count = sum(1 for e in entries if e["anon"])
    print(f"✓  Wrote {OUT_PATH}")
    print(f"   {n} contributions · {countries} countries · {anon_count} anonymous")


if __name__ == "__main__":
    main()
