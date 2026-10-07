"""Generates every SVG used by the profile README, in light and dark variants.

    python3 assets/build.py

Edit the content below, re-run, commit. Nothing else to install.
Contribution data is fetched with $GITHUB_TOKEN (or the local `gh` login) and
cached in contributions.json, so the build still works offline.
"""
import json
import os
import subprocess
import urllib.request
from datetime import date
from pathlib import Path
from textwrap import wrap
from xml.sax.saxutils import escape

OUT = Path(__file__).parent

THEMES = {
    "light": dict(ink="#1f2328", soft="#57606a", muted="#8c959f", line="#d0d7de", faint="#eaeef2"),
    "dark":  dict(ink="#e6edf3", soft="#9198a1", muted="#656d76", line="#30363d", faint="#21262d"),
}

MONO = 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace'
SANS = '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif'

USER = "SHINO-01"
W = 960  # full-width pieces share this width so everything lines up on one left edge

PROJECTS = {
    "now": [
        ("rolestash", "A private job-application tracker. One-click capture from any posting to a local kanban board. No AI, no inbox scraping.", ["typescript", "chrome ext"]),
        ("autocolavoid", "Satellite collision avoidance: orbit propagation, conjunction screening and maneuver recommendation.", ["rust", "fastapi", "timescale"]),
    ],
    "before": [
        ("rtd mono repo", "AI-generated code documentation, pulled from child repositories into one versioned site.", ["python", "mkdocs"]),
        ("eventure ai", "A multi-agent network that plans trips, guides tours and books tickets. Hackathon build.", ["python", "crewai"]),
        ("sign translator", "Real-time sign language translation from the holistic keypoints of the speaker's body.", ["python", "vision"]),
        ("mod rag", "A retrieval-augmented prototype for an agentic documentation chatbot.", ["python", "rag"]),
    ],
}

TOOLS = [
    ("languages", "typescript  ·  python  ·  rust  ·  go"),
    ("frameworks", "react  ·  fastapi  ·  django  ·  flask"),
    ("data", "postgres  ·  timescaledb"),
    ("ai", "crewai  ·  rag pipelines  ·  multi-agent systems"),
]


def svg(w, h, body, c, extra_css=""):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none">
<style>
  .mono {{ font-family: {MONO}; }}
  .sans {{ font-family: {SANS}; }}
  .ink {{ fill: {c['ink']}; }} .soft {{ fill: {c['soft']}; }} .muted {{ fill: {c['muted']}; }}
  {extra_css}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
</style>
{body}
</svg>
"""


def header(c):
    cx, cy = W - 120, 150
    css = f"""
  .orbit {{ transform-origin: {cx}px {cy}px; animation: spin 30s linear infinite; }}
  .orbit2 {{ transform-origin: {cx}px {cy}px; animation: spin 12s linear infinite reverse; }}
  .rise {{ opacity: 0; animation: rise 1.2s cubic-bezier(.2,.7,.2,1) forwards; }}
  .d2 {{ animation-delay: .25s; }} .d3 {{ animation-delay: .5s; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  @keyframes rise {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}"""
    body = f"""
<g class="rise"><text x="0" y="70" class="mono muted" font-size="15" letter-spacing="4">SHINO-01</text></g>
<g class="rise d2"><text x="-4" y="150" class="sans ink" font-size="76" font-weight="300" letter-spacing="-2.5">Sakif Hussain</text></g>
<g class="rise d3">
  <line x1="0" y1="190" x2="48" y2="190" stroke="{c['ink']}" stroke-width="1.5"/>
  <text x="0" y="230" class="mono soft" font-size="17">software engineer · builds small tools and quiet interfaces</text>
</g>
<circle cx="{cx}" cy="{cy}" r="96" stroke="{c['line']}" stroke-width="1"/>
<circle cx="{cx}" cy="{cy}" r="56" stroke="{c['line']}" stroke-width="1" stroke-dasharray="1 7" stroke-linecap="round"/>
<circle cx="{cx}" cy="{cy}" r="4.5" fill="{c['ink']}"/>
<g class="orbit"><circle cx="{cx + 96}" cy="{cy}" r="4" fill="{c['ink']}"/></g>
<g class="orbit2"><circle cx="{cx}" cy="{cy - 56}" r="2.5" fill="{c['muted']}"/></g>"""
    return svg(W, 280, body, c, css)


def section(c, num, title):
    tx = 52 + len(title) * 13 + 24
    body = f"""
<text x="0" y="34" class="mono muted" font-size="14" letter-spacing="2">{num}</text>
<text x="52" y="35" class="sans ink" font-size="22" font-weight="400">{escape(title)}</text>
<line x1="{tx}" y1="29" x2="{W}" y2="29" stroke="{c['line']}" stroke-width="1"/>"""
    return svg(W, 56, body, c)


GAP = 12  # gutter between cards, split across each card's inner edge


def card(c, idx, name, desc, tags, side):
    """side: 'l' or 'r'. Each card carries half the gutter so two 50% images tile flush."""
    w, h = 480, 236
    x0 = 0.5 if side == "l" else GAP / 2 + 0.5
    x1 = w - GAP / 2 - 0.5 if side == "l" else w - 0.5
    cw = x1 - x0
    px = x0 + 32
    lines = wrap(desc, 50)[:3]
    desc_svg = "".join(
        f'<text x="{px}" y="{116 + i * 23}" class="sans soft" font-size="15.5">{escape(l)}</text>' for i, l in enumerate(lines)
    )
    tag_text = "   ".join(t.upper() for t in tags)
    bottom = h - GAP - 0.5
    ax = x1 - 32
    body = f"""
<rect x="{x0}" y="0.5" width="{cw}" height="{bottom - 0.5}" rx="14" stroke="{c['line']}"/>
<text x="{px}" y="46" class="mono muted" font-size="13" letter-spacing="2">{idx:02d}</text>
<path d="M{ax - 12} 44 L{ax} 32 M{ax - 10} 32 H{ax} V42" stroke="{c['muted']}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
<text x="{px - 1}" y="86" class="sans ink" font-size="27" font-weight="400" letter-spacing="-0.5">{escape(name)}</text>
{desc_svg}
<line x1="{px}" y1="{bottom - 46}" x2="{x1 - 32}" y2="{bottom - 46}" stroke="{c['faint']}" stroke-width="1"/>
<text x="{px}" y="{bottom - 20}" class="mono muted" font-size="12" letter-spacing="1.6">{escape(tag_text)}</text>"""
    return svg(w, h, body, c)


def tools(c):
    rows = "".join(
        f'<text x="0" y="{30 + i * 40}" class="mono muted" font-size="13" letter-spacing="2">{label.upper()}</text>'
        f'<text x="200" y="{30 + i * 40}" class="mono soft" font-size="16">{escape(val)}</text>'
        + (f'<line x1="0" y1="{46 + i * 40}" x2="{W}" y2="{46 + i * 40}" stroke="{c["faint"]}" stroke-width="1"/>' if i < len(TOOLS) - 1 else "")
        for i, (label, val) in enumerate(TOOLS)
    )
    return svg(W, 30 + (len(TOOLS) - 1) * 40 + 14, rows, c)


def footer(c):
    cx, cy = W / 2, 60
    css = f".orbit {{ transform-origin: {cx}px {cy}px; animation: spin 20s linear infinite; }} @keyframes spin {{ to {{ transform: rotate(360deg); }} }}"
    body = f"""
<line x1="0" y1="{cy}" x2="{cx - 44}" y2="{cy}" stroke="{c['line']}"/>
<line x1="{cx + 44}" y1="{cy}" x2="{W}" y2="{cy}" stroke="{c['line']}"/>
<circle cx="{cx}" cy="{cy}" r="22" stroke="{c['line']}"/>
<circle cx="{cx}" cy="{cy}" r="3" fill="{c['ink']}"/>
<g class="orbit"><circle cx="{cx + 22}" cy="{cy}" r="2.5" fill="{c['ink']}"/></g>
<text x="{cx}" y="{cy + 66}" text-anchor="middle" class="mono muted" font-size="14" letter-spacing="3">SLOWLY, ON PURPOSE.</text>"""
    return svg(W, 140, body, c, css)


CAL_QUERY = """query($login: String!) { user(login: $login) { contributionsCollection { contributionCalendar {
  totalContributions weeks { contributionDays { date contributionCount contributionLevel } } } } } }"""


def fetch_calendar():
    cache = OUT / "contributions.json"
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        try:
            token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            token = None
    if token:
        try:
            req = urllib.request.Request(
                "https://api.github.com/graphql",
                data=json.dumps({"query": CAL_QUERY, "variables": {"login": USER}}).encode(),
                headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                cal = json.load(r)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
            cache.write_text(json.dumps(cal, indent=1))
            return cal
        except Exception as e:  # network or auth trouble: fall back to the cache
            print(f"contributions: using cache ({e})")
    return json.loads(cache.read_text())


LEVEL = {"NONE": 0, "FIRST_QUARTILE": 0.28, "SECOND_QUARTILE": 0.5, "THIRD_QUARTILE": 0.74, "FOURTH_QUARTILE": 1}


def activity(c, cal):
    cell, top = 13, 30
    weeks = cal["weeks"]
    pitch = (W - cell) / (len(weeks) - 1)  # span the shared column edge to edge
    x_off = 0
    cells, months, last_month = [], [], None
    for wi, week in enumerate(weeks):
        x = round(x_off + wi * pitch, 2)
        first = date.fromisoformat(week["contributionDays"][0]["date"])
        if first.month != last_month and first.day <= 7 and wi < len(weeks) - 2:
            months.append(f'<text x="{x}" y="14" class="mono muted" font-size="12" letter-spacing="1">{first.strftime("%b").upper()}</text>')
        last_month = first.month
        col = []
        for day in week["contributionDays"]:
            d = date.fromisoformat(day["date"])
            y = top + d.isoweekday() % 7 * pitch
            lv = LEVEL[day["contributionLevel"]]
            fill = f'fill="{c["ink"]}" fill-opacity="{lv}"' if lv else f'fill="{c["faint"]}"'
            col.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" {fill}><title>{day["contributionCount"]} on {day["date"]}</title></rect>')
        cells.append(f'<g class="col" style="animation-delay:{wi * 14}ms">{"".join(col)}</g>')
    base = top + 7 * pitch + 22
    legend_x = W - cell - 4 * 18
    legend = "".join(
        f'<rect x="{legend_x + i * 18}" y="{base - 11}" width="{cell}" height="{cell}" rx="3" '
        + (f'fill="{c["ink"]}" fill-opacity="{lv}"' if lv else f'fill="{c["faint"]}"') + "/>"
        for i, lv in enumerate([0, .28, .5, .74, 1])
    )
    css = """.col { opacity: 0; animation: in .6s ease-out forwards; }
  @keyframes in { to { opacity: 1; } }"""
    body = f"""{"".join(months)}
{"".join(cells)}
<text x="{x_off}" y="{base}" class="mono soft" font-size="13" letter-spacing="1">{cal["totalContributions"]} CONTRIBUTIONS · PAST YEAR</text>
<text x="{legend_x - 14}" y="{base}" text-anchor="end" class="mono muted" font-size="12" letter-spacing="1">LESS</text>
{legend}"""
    return svg(W, base + 8, body, c, css)


def main():
    cal = fetch_calendar()
    files = {"header": header, "tools": tools, "footer": footer}
    sections = ["activity", *PROJECTS, "tools"]
    for theme, c in THEMES.items():
        for name, fn in files.items():
            (OUT / f"{name}-{theme}.svg").write_text(fn(c))
        (OUT / f"activity-{theme}.svg").write_text(activity(c, cal))
        for i, key in enumerate(sections, 1):
            (OUT / f"section-{key}-{theme}.svg").write_text(section(c, f"{i:02d}", key))
        n = 0
        for key, items in PROJECTS.items():
            for name, desc, tags in items:
                side = "l" if n % 2 == 0 else "r"
                n += 1
                (OUT / f"card-{name.replace(' ', '-')}-{theme}.svg").write_text(card(c, n, name, desc, tags, side))


if __name__ == "__main__":
    main()
