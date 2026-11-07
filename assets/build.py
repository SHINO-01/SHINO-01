"""Generates README.md and every SVG it shows, in light and dark variants.

    python3 assets/build.py

All words come from content.yml at the repo root; this file only holds layout.
Needs PyYAML (pip install pyyaml).
Contribution data is fetched with $PROFILE_TOKEN (or the local `gh` login) and
cached in contributions.json, so the build still works offline.

Type is set in Instrument Serif, Anton and JetBrains Mono (all SIL OFL, see fonts/).
The fonts are Latin subsets embedded into each SVG, so the profile renders the same
everywhere; fonts/metrics.json holds their advance widths for layout.
"""
import base64
import json
import math
import os
import re
import subprocess
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

OUT = Path(__file__).parent
ROOT = OUT.parent
FONTS = OUT / "fonts"
METRICS = json.loads((FONTS / "metrics.json").read_text())
CONTENT = yaml.safe_load((ROOT / "content.yml").read_text())

USER = CONTENT["user"]
W = 960  # full-width pieces share this width so everything lines up on one left edge

# Card fills are the same in both themes; they read as printed stock on either page.
INK, CREAM = "#15120f", "#f4ecdc"
STOCK = dict(verm="#ff6a45", mari="#f5b53f", jade="#6cc39b", ultra="#3d4fd8", rose="#f4a3b5", ink=INK)

THEMES = {
    "light": dict(
        bg="#f5eddd", bg2="#ebe1cc", ink="#1a1612", soft="#4b4238", muted="#8b7e6b", line="#d6c7ab", faint="#e3d7bf",
        verm="#e4431f", mari="#d98f0c", jade="#2e8c64", ultra="#3149d6", rose="#d9607f",
        heat=["#e2d6bd", "#a3d3b8", "#33a072", "#f0a91e", "#ec4a24"], grain=.13, border="#d6c7ab",
    ),
    "dark": dict(
        bg="#16130f", bg2="#1f1b16", ink="#f4ecdc", soft="#cbbfa8", muted="#8a7f6e", line="#3b342c", faint="#2a2520",
        verm="#ff5d3a", mari="#f5b53f", jade="#5cb88f", ultra="#7d93ff", rose="#f4a3b5",
        heat=["#2e2924", "#2f7a5c", "#5ec897", "#f7b941", "#ff5d3a"], grain=.07, border="#2e2822",
    ),
}

COLOURS = dict(red="verm", yellow="mari", green="jade", blue="ultra", pink="rose", black="ink")


class _Keep(dict):
    def __missing__(self, key):  # leave unknown {placeholders} visible rather than crash
        return "{" + key + "}"


def fill(template, **values):
    return str(template).format_map(_Keep(values))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ── type ─────────────────────────────────────────────────────────────────────

FACES = {  # css class -> (metrics key, family, style, weight, file)
    "serif": ("serif", "SH Instrument", "normal", 400, "InstrumentSerif-Regular"),
    "ital": ("serif-italic", "SH Instrument", "italic", 400, "InstrumentSerif-Italic"),
    "anton": ("anton", "SH Anton", "normal", 400, "Anton-Regular"),
    "mono": ("mono", "SH Mono", "normal", 400, "JetBrainsMono-Regular"),
    "monob": ("mono-bold", "SH Mono", "normal", 600, "JetBrainsMono-SemiBold"),
}
FALLBACK = {
    "SH Instrument": 'Georgia, "Times New Roman", serif',
    "SH Anton": 'Impact, "Arial Narrow", sans-serif',
    "SH Mono": 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
}


def tw(s, cls, size, ls=0.0):
    """Rendered width of `s` in face `cls` at `size` px with letter-spacing `ls`."""
    m = METRICS[FACES[cls][0]]
    return sum(m.get(ch, .55) for ch in s) * size + ls * len(s)


def fit(s, cls, size, maxw, ls=0.0):
    while size > 8 and tw(s, cls, size, ls) > maxw:
        size -= 1
    return size


def wrap_px(s, cls, size, maxw):
    lines, cur = [], ""
    for word in s.split():
        nxt = f"{cur} {word}".strip()
        if cur and tw(nxt, cls, size) > maxw:
            lines.append(cur)
            cur = word
        else:
            cur = nxt
    return lines + [cur] if cur else lines


def T(x, y, s, cls, size, fill, ls=0, anchor=None, extra=""):
    a = f' text-anchor="{anchor}"' if anchor else ""
    l = f' letter-spacing="{ls}"' if ls else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" font-size="{size}" fill="{fill}"{l}{a}{extra}>{escape(s)}</text>'


def font_css(body):
    used = {cls for cls in FACES if re.search(rf'class="[^"]*\b{cls}\b', body)}
    css = []
    for cls in sorted(used):
        _, fam, style, weight, file = FACES[cls]
        data = base64.b64encode((FONTS / f"{file}.woff2").read_bytes()).decode()
        css.append(f'@font-face {{ font-family: "{fam}"; font-style: {style}; font-weight: {weight}; '
                   f'src: url(data:font/woff2;base64,{data}) format("woff2"); }}')
        css.append(f'.{cls} {{ font-family: "{fam}", {FALLBACK[fam]}; font-style: {style}; font-weight: {weight}; }}')
    return "\n  ".join(css)


def svg(w, h, body, css="", defs=""):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none">
<defs>
<style>
  {font_css(body)}
  {css}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
</style>
{defs}
</defs>
{body}
</svg>
"""


def panel(c, w, h, content, fill=None, css="", defs="", rect=(0.5, 0.5), rx=22, stroke=None):
    """A filled, grain-textured sheet. Everything in `content` is clipped to its rounded edge."""
    x, y = rect[:2]
    pw = rect[2] if len(rect) > 2 else w - 2 * x
    ph = rect[3] if len(rect) > 3 else h - 2 * y
    grain = f"""
<clipPath id="sheet"><rect x="{x}" y="{y}" width="{pw}" height="{ph}" rx="{rx}"/></clipPath>
<filter id="grain" x="0" y="0" width="100%" height="100%">
  <feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="3" stitchTiles="stitch"/>
  <feColorMatrix type="saturate" values="0"/>
</filter>"""
    body = f"""<g clip-path="url(#sheet)">
<rect x="{x}" y="{y}" width="{pw}" height="{ph}" fill="{fill or c['bg']}"/>
{content}
<rect x="{x}" y="{y}" width="{pw}" height="{ph}" filter="url(#grain)" opacity="{c['grain']}"/>
</g>
<rect x="{x}" y="{y}" width="{pw}" height="{ph}" rx="{rx}" stroke="{stroke or c['border']}"/>"""
    return svg(w, h, body, css, grain + defs)


def orbiter(cx, cy, rx, squash, rot, mark, dur, reverse=False):
    """A mark that travels an ellipse tilted by `rot` degrees (SMIL, so it works inside <img>)."""
    ry = rx * squash
    sweep = 0 if reverse else 1
    d = f"M{cx - rx} {cy} a{rx} {ry:.1f} 0 1 {sweep} {2 * rx} 0 a{rx} {ry:.1f} 0 1 {sweep} {-2 * rx} 0"
    return (f'<g transform="rotate({rot} {cx} {cy})"><g>{mark}'
            f'<animateMotion dur="{dur}s" repeatCount="indefinite" path="{d}"/></g></g>')


def sparkle(cx, cy, r, fill, extra=""):
    k = r * .18
    return (f'<path d="M{cx} {cy - r} C{cx + k} {cy - k} {cx + k} {cy - k} {cx + r} {cy} '
            f'C{cx + k} {cy + k} {cx + k} {cy + k} {cx} {cy + r} C{cx - k} {cy + k} {cx - k} {cy + k} {cx - r} {cy} '
            f'C{cx - k} {cy - k} {cx - k} {cy - k} {cx} {cy - r}Z" fill="{fill}"{extra}/>')


def masthead(c, y, left, mid, right, x0=36, x1=W - 36):
    return (T(x0, y, left, "monob", 11, c["ink"], 2.2)
            + (T(W / 2, y, mid, "mono", 11, c["muted"], 2.2, "middle") if mid else "")
            + T(x1, y, right, "mono", 11, c["muted"], 2.2, "end")
            + f'<line x1="{x0}" y1="{y + 14}" x2="{x1}" y2="{y + 14}" stroke="{c["ink"]}" stroke-width="1.6"/>'
            + f'<line x1="{x0}" y1="{y + 18.5}" x2="{x1}" y2="{y + 18.5}" stroke="{c["ink"]}" stroke-width=".6"/>')


# ── header ───────────────────────────────────────────────────────────────────

def header(c):
    t = CONTENT["header"]
    cx, cy, R = 772, 262, 132
    m = t["masthead"]
    out = [masthead(c, 40, m["left"].upper(), m["middle"].upper(), m["right"].upper())]

    # the name, set large and layered
    last = t["last_name"].upper()
    hs = fit(last, "anton", 150, 560, 2)
    fs = fit(t["first_name"], "ital", 210, 560, -4)
    out.append(T(30, 392, last, "anton", hs, c["verm"], 2))
    out.append(T(22, 250, t["first_name"], "ital", fs, c["ink"], -4))
    out.append(sparkle(min(30 + tw(last, "anton", hs, 2) + 24, 580), 300, 14, c["mari"]))

    # orbital dial
    ticks = []
    for i in range(72):
        a = math.radians(i * 5)
        r0 = R + 8 if i % 6 else R + 2
        ticks.append(f'<line x1="{cx + r0 * math.cos(a):.1f}" y1="{cy + r0 * math.sin(a):.1f}" '
                     f'x2="{cx + (R + 14) * math.cos(a):.1f}" y2="{cy + (R + 14) * math.sin(a):.1f}" '
                     f'stroke="{c["muted"] if i % 6 else c["ink"]}" stroke-width="{1 if i % 6 else 1.6}"/>')
    rt = R + 32
    ring_text = t["ring"].upper() + "  ·  "
    rs = fit(ring_text, "monob", 11.5, 2 * math.pi * rt * .9)
    ls = (2 * math.pi * rt - tw(ring_text, "monob", rs)) / len(ring_text)
    dial = t["dial"]
    out.append(f"""
<circle cx="{cx}" cy="{cy}" r="{R + 52}" fill="{c['bg2']}"/>
<circle cx="{cx}" cy="{cy}" r="{R + 52}" stroke="{c['line']}"/>
<circle cx="{cx}" cy="{cy}" r="{R + 14}" stroke="{c['line']}"/>
{''.join(ticks)}
<path id="ring" d="M{cx - rt} {cy} a{rt} {rt} 0 1 1 {2 * rt} 0 a{rt} {rt} 0 1 1 {-2 * rt} 0"/>
<g class="slow"><text class="monob" font-size="{rs}" fill="{c['soft']}" letter-spacing="{ls:.3f}"><textPath href="#ring">{escape(ring_text)}</textPath></text></g>
<circle cx="{cx}" cy="{cy}" r="{R - 34}" stroke="{c['muted']}" stroke-dasharray="1 6" stroke-linecap="round"/>
<ellipse id="o1" cx="{cx}" cy="{cy}" rx="{R - 6}" ry="{(R - 6) * .32:.1f}" transform="rotate(-24 {cx} {cy})" stroke="{c['jade']}" stroke-width="1.4"/>
<ellipse id="o2" cx="{cx}" cy="{cy}" rx="{R - 22}" ry="{(R - 22) * .45:.1f}" transform="rotate(38 {cx} {cy})" stroke="{c['ultra']}" stroke-width="1.4"/>
<circle cx="{cx}" cy="{cy}" r="30" fill="{c['mari']}"/>
<clipPath id="planet"><circle cx="{cx}" cy="{cy}" r="30"/></clipPath>
<g clip-path="url(#planet)" stroke="{c['verm']}" stroke-width="2.2">{''.join(f'<line x1="{cx - 40}" y1="{cy - 30 + i * 7}" x2="{cx + 40}" y2="{cy - 30 + i * 7}" opacity="{min(1, i / 8):.2f}"/>' for i in range(1, 10))}</g>
{orbiter(cx, cy, R - 6, .32, -24, f'<circle r="5" fill="{c['ink']}"/><circle r="10" stroke="{c['ink']}" opacity=".35"/>', 16)}
{orbiter(cx, cy, R - 22, .45, 38, f'<rect x="-4.5" y="-4.5" width="9" height="9" fill="{c['verm']}" transform="rotate(45)"/>', 9, reverse=True)}
{T(cx + R - 2, cy - 44, str(dial["top"]).upper(), "monob", 9.5, c['jade'], 1.5)}
{T(cx - R + 10, cy + 70, str(dial["bottom"]).upper(), "monob", 9.5, c['ultra'], 1.5)}
{T(cx, cy + R - 44, str(dial["centre"]).upper(), "monob", 10, c['muted'], 1.5, "middle")}""")

    # tagline and intro
    y = 452
    out.append(f'<line x1="36" y1="{y - 26}" x2="84" y2="{y - 26}" stroke="{c["verm"]}" stroke-width="3"/>')
    tag = wrap_px(t["tagline"], "ital", 34, 540)
    for i, line in enumerate(tag):
        out.append(T(36, y + 8 + i * 38, line, "ital", 34, c["ink"]))
    y += 8 + 38 * len(tag) + 4
    intro = wrap_px(t["intro"], "mono", 12.5, 560)
    for i, line in enumerate(intro):
        out.append(T(36, y + i * 20, line, "mono", 12.5, c["soft"]))
    cap = t["caption"]
    out.append(T(W - 36, y, cap["label"].upper(), "monob", 10, c["muted"], 2, "end"))
    out.append(T(W - 36, y + 18, cap["text"], "ital", 17, c["soft"], 0, "end"))

    # ticker, sitting below however long the intro runs
    tband = max(642, y + 20 * (len(intro) - 1) + 42)
    H = tband + 62
    seq, x = [], 0.0
    for item in t["ticker"]:
        s = item.upper()
        seq.append(T(x, tband + 41, s, "anton", 30, INK, 1))
        x += tw(s, "anton", 30, 1) + 22
        seq.append(sparkle(x, tband + 30, 9, INK))
        x += 22
    L = x
    copies = "".join(f'<g transform="translate({k * L:.1f} 0)">{"".join(seq)}</g>' for k in range(math.ceil(W / L) + 1))
    out.append(f'<rect x="0" y="{tband}" width="{W}" height="62" fill="{c["verm"]}"/>'
               f'<line x1="0" y1="{tband}" x2="{W}" y2="{tband}" stroke="{c["ink"]}" stroke-width="1.6"/>'
               f'<g class="tick">{copies}</g>')

    css = f"""
  .slow {{ transform-origin: {cx}px {cy}px; animation: spin 90s linear infinite; }}
  .tick {{ animation: tick {max(30, L / 26):.0f}s linear infinite; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  @keyframes tick {{ to {{ transform: translateX(-{L:.1f}px); }} }}"""
    return panel(c, W, H, "\n".join(out), css=css)


# ── activity: the centrepiece ────────────────────────────────────────────────

CAL_QUERY = """query($login: String!) { user(login: $login) { contributionsCollection { contributionCalendar {
  totalContributions weeks { contributionDays { date contributionCount contributionLevel } } } } } }"""


def fetch_calendar():
    cache = OUT / "contributions.json"
    # Needs a token that can see the user's contributions: a personal token (PROFILE_TOKEN in CI)
    # or the local gh login. The default Actions GITHUB_TOKEN sees none and returns an empty year.
    token = os.environ.get("PROFILE_TOKEN")
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
            if cal["totalContributions"] == 0 and cache.exists():
                raise ValueError("empty calendar; token probably can't see contributions")
            cache.write_text(json.dumps(cal, indent=1))
            return cal
        except Exception as e:  # network or auth trouble: fall back to the cache
            print(f"contributions: using cache ({e})")
    return json.loads(cache.read_text())


LEVEL = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
DOW = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


def stats(cal):
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    counts = [d["contributionCount"] for d in days]
    longest = run = 0
    for n in counts:
        run = run + 1 if n else 0
        longest = max(longest, run)
    tail = counts[:-1] if counts and not counts[-1] else counts  # today may still be in progress
    current = 0
    for n in reversed(tail):
        if not n:
            break
        current += 1
    peak = max(days, key=lambda d: d["contributionCount"])
    months, weekdays = defaultdict(int), [0] * 7
    for d in days:
        dt = date.fromisoformat(d["date"])
        months[dt.strftime("%Y-%m")] += d["contributionCount"]
        weekdays[dt.isoweekday() % 7] += d["contributionCount"]
    best_month = max(months, key=months.get)
    return dict(
        total=cal["totalContributions"], active=sum(1 for n in counts if n), span=len(days),
        longest=longest, current=current, peak=peak, weekdays=weekdays,
        month=(date.fromisoformat(best_month + "-01"), months[best_month]),
        today=date.fromisoformat(days[-1]["date"]),
    )


def fmt(d):
    return f"{d.day:02d} {d.strftime('%b').upper()} {d.year}"


def activity(c, cal):
    st = stats(cal)
    heat = c["heat"]
    weeks = cal["weeks"]
    n = len(weeks)
    t = CONTENT["activity"]
    ctx = dict(total=f"{st['total']:,}", active=st["active"], quiet=st["span"] - st["active"], span=st["span"],
               longest=st["longest"], current=st["current"], today=fmt(st["today"]))
    f = lambda template, **extra: fill(template, **ctx, **extra)
    out = [masthead(c, 40, f"№ 01 — {f(t['title'])}".upper(), "", f(t["as_of"]).upper())]

    # the headline number
    out.append(T(36, 98, f(t["figure"]).upper(), "monob", 10.5, c["muted"], 2))
    total = f"{st['total']:,}"
    ns = fit(total, "anton", 176, 300)
    out.append(T(30, 266, total, "anton", ns, c["mari"], 1))
    nx = 30 + tw(total, "anton", ns, 1) + 22
    for i, line in enumerate(t["headline"][:2]):
        line = f(line)
        out.append(T(nx, 204 + i * 42, line, "ital", fit(line, "ital", 40, 560 - nx), c["soft"] if i else c["ink"]))
    out.append(sparkle(nx + 6, 140, 10, c["verm"]))

    # stat grid
    gx, gy, cw, ch = 588, 82, 168, 62
    peak = st["peak"]
    pd = date.fromisoformat(peak["date"])
    m_date, m_total = st["month"]
    fav = max(range(7), key=lambda i: st["weekdays"][i])
    plural = lambda v: "" if v == 1 else "s"
    values = {  # key in content.yml -> (shown value, extra template fields, accent)
        "active_days": (st["active"], {}, c["jade"]),
        "longest_run": (st["longest"], {"s": plural(st["longest"])}, c["mari"]),
        "current_run": (st["current"], {"s": plural(st["current"])}, c["verm"]),
        "loudest_day": (peak["contributionCount"], {"count": peak["contributionCount"],
                        "date": f"{pd.day} {pd.strftime('%b').lower()}"}, c["verm"]),
        "busiest_month": (m_date.strftime("%b").upper(), {"count": m_total}, c["ultra"]),
        "favourite_day": (DOW[fav][:3].upper(), {}, c["rose"]),
    }
    cells = []
    for key, spec in t["stats"].items():
        val, extra, accent = values[key]
        cells.append((f(spec["label"], **extra).upper(), str(val), f(spec["unit"], **extra), accent))
    for i, (label, val, unit, accent) in enumerate(cells[:6]):
        x, y = gx + (i % 2) * cw, gy + (i // 2) * ch
        out.append(f'<circle cx="{x + 16}" cy="{y + 18.5}" r="3.5" fill="{accent}"/>')
        out.append(T(x + 26, y + 22, label, "monob", 9.5, c["muted"], 1.6))
        out.append(T(x + 12, y + 55, val, "anton", 30, c["ink"], .5))
        out.append(T(x + 12 + tw(val, "anton", 30, .5) + 8, y + 55, unit, "ital", 18, c["soft"]))
        if i % 2 == 0:
            out.append(f'<line x1="{x + cw}" y1="{y + 8}" x2="{x + cw}" y2="{y + ch - 8}" stroke="{c["line"]}"/>')
        if i < 4 and i % 2 == 0:
            out.append(f'<line x1="{gx + 8}" y1="{y + ch}" x2="{gx + 2 * cw}" y2="{y + ch}" stroke="{c["line"]}"/>')

    # the tiles: the year split into two half-year strips, so each tile can be large
    half = math.ceil(n / 2)
    x0, x1 = 92, W - 40
    pitch = (x1 - x0) / (half - 1 + .84)
    cell = pitch * .84
    sky_h = 44
    wt = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]
    wmax = max(wt) or 1
    pw = max(range(n), key=lambda i: wt[i])
    peak_xy = today_xy = None
    glows, cols = [], []
    y = 300
    for s, chunk in enumerate([range(0, half), range(half, n)]):
        sky_base, months_y = y + sky_h, y + sky_h + 26
        grid_top = months_y + 12
        tx, ty, twd, th = 58, months_y - 22, x1 + 16 - 58, 7 * pitch + 46
        # weekly skyline (square-root scale, so quiet weeks still register)
        out.append(f'<line x1="{x0}" y1="{sky_base + .5}" x2="{x1}" y2="{sky_base + .5}" stroke="{c["line"]}"/>')
        wt_words = t["week_totals"].upper().split(maxsplit=1)
        for j, word in enumerate(reversed(wt_words)):
            out.append(T(x0 - 12, sky_base - 2 - j * 12, word, "monob", 8.5, c["muted"], 1.4, "end"))
        for k, wi in enumerate(chunk):
            x = x0 + k * pitch
            lv = max(LEVEL[d["contributionLevel"]] for d in weeks[wi]["contributionDays"])
            if wt[wi]:
                h = max(3, math.sqrt(wt[wi] / wmax) * sky_h)
                out.append(f'<rect class="bar" style="animation-delay:{300 + wi * 16}ms" x="{x:.2f}" y="{sky_base - h:.2f}" '
                           f'width="{cell:.2f}" height="{h:.2f}" rx="2.5" fill="{heat[max(lv, 1)]}"><title>{escape(f(t["tooltips"]["week"], count=wt[wi]))}</title></rect>')
                if wi == pw:
                    out.append(T(x + cell / 2, sky_base - h - 6, str(wt[wi]), "monob", 9.5, c["ink"], 0, "middle"))
            else:
                out.append(f'<rect x="{x:.2f}" y="{sky_base - 1.5:.2f}" width="{cell:.2f}" height="1.5" fill="{c["line"]}"/>')

        out.append(f'<rect x="{tx}" y="{ty}" width="{twd}" height="{th}" rx="16" fill="{c["bg2"]}" stroke="{c["line"]}"/>')
        for (px, py, sx, sy) in [(tx, ty, -1, -1), (tx + twd, ty, 1, -1), (tx, ty + th, -1, 1), (tx + twd, ty + th, 1, 1)]:
            out.append(f'<path d="M{px + sx * 6} {py} h{sx * 10} M{px} {py + sy * 6} v{sy * 10}" stroke="{c["muted"]}"/>')
        for row, label in zip([1, 3, 5], [str(d).upper() for d in t["day_labels"]]):
            out.append(T(x0 - 12, grid_top + row * pitch + cell * .64, label, "monob", 9, c["muted"], 1, "end"))

        last_month = None
        for k, wi in enumerate(chunk):
            week = weeks[wi]
            x = x0 + k * pitch
            first = date.fromisoformat(week["contributionDays"][0]["date"])
            if first.month != last_month and (first.day <= 7 or k == 0) and k < len(chunk) - 1:
                label = first.strftime("%b").upper() + (f" '{first.year % 100:02d}" if first.month == 1 or k == 0 else "")
                out.append(T(x, months_y, label, "monob", 10, c["soft"], 1.4))
                if k:
                    out.append(f'<line x1="{x - (pitch - cell) / 2:.2f}" y1="{months_y + 4}" x2="{x - (pitch - cell) / 2:.2f}" y2="{grid_top + 7 * pitch:.2f}" stroke="{c["line"]}" stroke-dasharray="1 3"/>')
            last_month = first.month
            col = []
            for day in week["contributionDays"]:
                d = date.fromisoformat(day["date"])
                yy = grid_top + d.isoweekday() % 7 * pitch
                lv, cnt = LEVEL[day["contributionLevel"]], day["contributionCount"]
                col.append(f'<rect x="{x:.2f}" y="{yy:.2f}" width="{cell:.2f}" height="{cell:.2f}" rx="5" fill="{heat[lv]}">'
                           f'<title>{escape(f(t["tooltips"]["day"], count=cnt, date=day["date"]))}</title></rect>')
                if not lv:
                    col.append(f'<circle cx="{x + cell / 2:.2f}" cy="{yy + cell / 2:.2f}" r="1.3" fill="{c["muted"]}" opacity=".45"/>')
                elif lv >= 3:
                    col.append(T(x + cell / 2, yy + cell / 2 + 3.4, str(cnt), "monob", 9.5 if cnt < 100 else 8, INK, 0, "middle"))
                if lv == 4:
                    glows.append(f'<rect class="glow" style="animation-delay:{(wi * 7 + d.weekday()) % 9 * .3:.1f}s" x="{x - 3:.2f}" y="{yy - 3:.2f}" '
                                 f'width="{cell + 6:.2f}" height="{cell + 6:.2f}" rx="8" fill="{heat[4]}" filter="url(#bloom)"/>')
                if day is peak:
                    peak_xy = (x, yy, sky_base - sky_h)
                if d == st["today"]:
                    today_xy = (x, yy)
            cols.append(f'<g class="col" style="animation-delay:{wi * 14}ms">{"".join(col)}</g>')
        out += glows + cols
        glows, cols = [], []
        y = ty + th + 22

    if today_xy:
        x, yy = today_xy
        out.append(f'<rect x="{x - 3:.2f}" y="{yy - 3:.2f}" width="{cell + 6:.2f}" height="{cell + 6:.2f}" rx="7" stroke="{c["ink"]}" stroke-width="1.6"/>')
        out.append(T(x + cell + 2, yy + cell + 18, t["today"].upper(), "monob", 8.5, c["ink"], 1.2, "end"))

    # callout on the loudest day, routed along a gutter so it never covers a tile
    if peak_xy and peak["contributionCount"]:
        x, yy, top = peak_xy
        left = x > W / 2
        gut = x - (pitch - cell) / 2 if left else x + cell + (pitch - cell) / 2
        ly = top + 6
        tx_end = gut - 12 if left else gut + 12
        anchor = "end" if left else "start"
        t1 = f(t["loudest"]["title"])
        t2 = f(t["loudest"]["detail"], count=peak["contributionCount"], weekday=pd.strftime("%a"), date=fmt(pd)).upper()
        bw = max(tw(t1, "ital", 26), tw(t2, "monob", 9.5, 1.2)) + 16
        bx = tx_end - bw + 8 if left else tx_end - 8
        out.append(f'<rect x="{bx:.1f}" y="{ly - 24}" width="{bw:.1f}" height="44" fill="{c["bg"]}"/>')
        out.append(f'<circle cx="{x + cell / 2:.2f}" cy="{yy + cell / 2:.2f}" r="{cell * .82:.2f}" stroke="{c["verm"]}" stroke-width="1.8"/>')
        out.append(f'<path d="M{gut:.2f} {yy + cell / 2 - cell * .82 - 1:.2f} V{ly - 6} H{tx_end + (4 if left else -4):.2f}" stroke="{c["verm"]}" stroke-width="1.2"/>')
        out.append(T(tx_end, ly, t1, "ital", 26, c["ink"], 0, anchor))
        out.append(T(tx_end, ly + 16, t2, "monob", 9.5, c["verm"], 1.2, anchor))

    # legend, weekly rhythm, peak week
    ly = y + 26
    low = t["legend"]["low"].upper()
    out.append(T(36, ly, low, "monob", 9.5, c["muted"], 1.5))
    lx = 36 + tw(low, "monob", 9.5, 1.5) + 10
    for i in range(5):
        out.append(f'<rect x="{lx + i * 22:.1f}" y="{ly - 13}" width="17" height="17" rx="4" fill="{heat[i]}"/>')
    out.append(T(lx + 5 * 22 + 4, ly, t["legend"]["high"].upper(), "monob", 9.5, c["muted"], 1.5))

    rx0 = 340
    rhythm = t["rhythm"]["label"].upper()
    out.append(T(rx0, ly, rhythm, "monob", 9.5, c["muted"], 1.5))
    letters = (str(t["rhythm"]["letters"]) + "       ")[:7]
    wmx = max(st["weekdays"]) or 1
    for i, v in enumerate(st["weekdays"]):
        bx = rx0 + max(74, tw(rhythm, "monob", 9.5, 1.5) + 14) + i * 22
        h = max(2, v / wmx * 28)
        out.append(f'<rect x="{bx}" y="{ly + 2 - h:.1f}" width="13" height="{h:.1f}" rx="2" fill="{c["verm"] if i == fav else c["jade"]}"/>')
        out.append(T(bx + 6.5, ly + 16, letters[i], "monob", 8.5, c["muted"], 0, "middle"))

    pw_start = date.fromisoformat(weeks[pw]["contributionDays"][0]["date"])
    out.append(T(W - 36, ly - 10, t["peak_week"]["label"].upper(), "monob", 9.5, c["muted"], 1.5, "end"))
    pw_text = f(t["peak_week"]["text"], count=wt[pw], date=f"{pw_start.day} {pw_start.strftime('%b').lower()}")
    out.append(T(W - 36, ly + 12, pw_text, "ital", 22, c["ink"], 0, "end"))

    # a closing line, in the voice of the rest of the page
    qy = ly + 40
    out.append(f'<line x1="36" y1="{qy}" x2="{W - 36}" y2="{qy}" stroke="{c["line"]}" stroke-dasharray="2 5"/>')
    out.append(sparkle(W / 2, qy, 8, c["mari"]))
    closing = f(t["closing"])
    out.append(T(W / 2, qy + 46, closing, "ital", fit(closing, "ital", 28, W - 72), c["soft"], 0, "middle"))
    H = round(qy + 78)

    defs = """<filter id="bloom" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3.5"/></filter>"""
    css = f"""
  .col {{ animation: fade .7s ease-out backwards; }}
  .bar {{ transform-box: fill-box; transform-origin: 50% 100%; animation: grow .9s cubic-bezier(.2,.8,.2,1) backwards; }}
  .glow {{ opacity: .55; animation: pulse 2.8s ease-in-out infinite alternate; }}
  @keyframes fade {{ from {{ opacity: 0; }} }}
  @keyframes grow {{ from {{ transform: scaleY(0); }} }}
  @keyframes pulse {{ from {{ opacity: .15; }} to {{ opacity: .85; }} }}"""
    return panel(c, W, H, "\n".join(out), css=css, defs=defs)


# ── section heads ────────────────────────────────────────────────────────────

def section(c, num, title, kicker, sub):
    H = 128
    nw = tw(num, "anton", 92, 1)
    tx = nw + 22
    ts = fit(title, "ital", 76, W - tx - tw(sub, "ital", 22) - 60, -1)
    ruler = "".join(
        f'<line x1="{x}" y1="{H - 10}" x2="{x}" y2="{H - (18 if x % 80 == 0 else 14)}" stroke="{c["muted"] if x % 80 else c["ink"]}"/>'
        for x in range(0, W + 1, 8)
    )
    body = f"""
{T(0, 96, num, "anton", 92, "none", 1, extra=f' stroke="{c["verm"]}" stroke-width="1.6"')}
{T(tx + 2, 34, kicker.upper(), "monob", 10.5, c["muted"], 2.4)}
{T(tx - 2, 96, title, "ital", ts, c["ink"], -1)}
{sparkle(tx + tw(title, "ital", ts, -1) + 16, 54, 11, c["mari"])}
{T(W, 96, sub, "ital", 22, c["soft"], 0, "end")}
<line x1="0" y1="{H - 10.5}" x2="{W}" y2="{H - 10.5}" stroke="{c["ink"]}" stroke-width="1.2"/>
{ruler}"""
    return svg(W, H, body)


# ── project cards ────────────────────────────────────────────────────────────

GAP = 14  # gutter between cards, split across each card's inner edge


def glyph(kind, gx, gy, col, label=""):
    """Line drawings in a 120px box, one per project."""
    s = f'stroke="{col}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'
    if kind == "kanban":
        out = []
        for ci, count in enumerate([3, 2, 4]):
            x = gx + ci * 42
            out.append(f'<rect x="{x}" y="{gy}" width="34" height="5" rx="2.5" fill="{col}"/>')
            for k in range(count):
                out.append(f'<rect x="{x}" y="{gy + 14 + k * 24}" width="34" height="18" rx="3.5" {s}/>')
        out.append(f'<g transform="rotate(-9 {gx + 60} {gy + 108})"><rect x="{gx + 44}" y="{gy + 98}" width="34" height="18" rx="3.5" fill="{col}"/></g>')
        out.append(f'<path d="M{gx + 40} {gy + 108} C{gx + 22} {gy + 108} {gx + 16} {gy + 96} {gx + 17} {gy + 86}" {s} stroke-dasharray="2 4"/>')
        return "".join(out)
    if kind == "orbit":
        cx, cy = gx + 60, gy + 60
        def pt(rx, ry, rot, t):
            x, y = rx * math.cos(t), ry * math.sin(t)
            r = math.radians(rot)
            return cx + x * math.cos(r) - y * math.sin(r), cy + x * math.sin(r) + y * math.cos(r)
        a = [pt(58, 20, -28, math.radians(i)) for i in range(360)]
        b = [pt(56, 26, 34, math.radians(i)) for i in range(360)]
        _, hit = min(((math.dist(p, q), p) for p in a[:180] for q in b[::2]), key=lambda t: t[0])
        return f"""<ellipse cx="{cx}" cy="{cy}" rx="58" ry="20" transform="rotate(-28 {cx} {cy})" {s}/>
<ellipse cx="{cx}" cy="{cy}" rx="56" ry="26" transform="rotate(34 {cx} {cy})" {s} stroke-dasharray="3 4"/>
<circle cx="{cx}" cy="{cy}" r="11" fill="{col}"/>
<circle cx="{hit[0]:.1f}" cy="{hit[1]:.1f}" r="12" {s} stroke-dasharray="2 3"/>
<circle cx="{hit[0] - 4:.1f}" cy="{hit[1] - 2:.1f}" r="3.2" fill="{col}"/><circle cx="{hit[0] + 4:.1f}" cy="{hit[1] + 3:.1f}" r="3.2" fill="{col}"/>
<path d="M{hit[0] + 16:.1f} {hit[1] - 16:.1f} l8 -8 m-6 0 h6 v6" {s}/>"""
    if kind == "tree":
        out = []
        for i in range(3):
            x = gx + i * 44
            out.append(f'<rect x="{x}" y="{gy}" width="32" height="22" rx="4" {s}/>')
            out.append(f'<path d="M{x + 16} {gy + 22} C{x + 16} {gy + 44} {gx + 60} {gy + 36} {gx + 60} {gy + 56}" {s}/>')
        for k in range(3):
            out.append(f'<rect x="{gx + 34 + k * 5}" y="{gy + 56 + k * 5}" width="46" height="58" rx="4" '
                       + (f'fill="{col}"' if k == 2 else s) + "/>")
        return "".join(out)
    if kind == "network":
        nodes = [(10, 20), (52, 8), (104, 26), (30, 70), (78, 60), (60, 110), (112, 96)]
        edges = [(0, 1), (1, 2), (0, 3), (1, 4), (2, 4), (3, 4), (3, 5), (4, 6), (5, 6), (4, 5)]
        route = [(0, 3), (3, 4), (4, 6)]
        out = [f'<line x1="{gx + nodes[a][0]}" y1="{gy + nodes[a][1]}" x2="{gx + nodes[b][0]}" y2="{gy + nodes[b][1]}" '
               f'stroke="{col}" stroke-width="{3 if (a, b) in route else 1.2}" stroke-linecap="round"'
               + ("" if (a, b) in route else ' stroke-dasharray="2 4"') + "/>" for a, b in edges]
        for i, (x, y) in enumerate(nodes):
            out.append(f'<circle cx="{gx + x}" cy="{gy + y}" r="{9 if i == 4 else 5}" '
                       + (f'fill="{col}"' if i in (0, 3, 6) else f'fill="none" {s}') + "/>")
        return "".join(out)
    if kind == "hand":
        wrist = (60, 116)
        fingers = [[(38, 98), (24, 82), (16, 68), (12, 56)], [(46, 78), (42, 54), (40, 38), (39, 24)],
                   [(58, 74), (58, 48), (58, 30), (58, 14)], [(70, 76), (73, 52), (75, 36), (76, 24)],
                   [(81, 84), (88, 66), (91, 54), (93, 44)]]
        out = []
        for f in fingers:
            pts = [wrist] + f
            out.append(f'<polyline points="{" ".join(f"{gx + x},{gy + y}" for x, y in pts)}" {s} fill="none"/>')
            out += [f'<circle cx="{gx + x}" cy="{gy + y}" r="{3.6 if j == 3 else 2.6}" fill="{col}"/>' for j, (x, y) in enumerate(f)]
        base = [f[0] for f in fingers]
        out.append(f'<polyline points="{" ".join(f"{gx + x},{gy + y}" for x, y in base)}" {s} fill="none" stroke-dasharray="2 4"/>')
        out.append(f'<circle cx="{gx + wrist[0]}" cy="{gy + wrist[1]}" r="5" fill="{col}"/>')
        return "".join(out)
    if kind == "rag":
        out = [f'<circle cx="{gx + 18}" cy="{gy + 60}" r="{r}" {s} opacity="{o}"/>' for r, o in [(12, 1), (24, .5), (36, .25)]]
        out.append(T(gx + 18, gy + 65, "?", "monob", 14, col, 0, "middle"))
        for k in range(4):
            y = gy + 8 + k * 28
            hit = k in (1, 2)
            out.append(f'<rect x="{gx + 70}" y="{y}" width="50" height="20" rx="3.5" ' + (f'fill="{col}"' if hit else s) + "/>")
            out.append(f'<line x1="{gx + 32}" y1="{gy + 60}" x2="{gx + 68}" y2="{y + 10}" stroke="{col}" '
                       + ('stroke-width="1.8"' if hit else 'stroke-width="1" stroke-dasharray="2 4"') + "/>")
        return "".join(out)
    if kind == "candles":
        out = [f'<line x1="{gx}" y1="{gy + 104}" x2="{gx + 120}" y2="{gy + 104}" {s} stroke-dasharray="2 4"/>']
        bars = [(70, 92, 76, 88), (60, 86, 82, 66), (52, 74, 66, 56), (58, 80, 60, 72), (34, 64, 70, 42), (20, 46, 42, 26), (6, 34, 30, 12)]
        for i, (hi, lo, o, cl) in enumerate(bars):
            x = gx + 6 + i * 17
            out.append(f'<line x1="{x + 5}" y1="{gy + hi}" x2="{x + 5}" y2="{gy + lo}" {s}/>')
            top, bot = min(o, cl), max(o, cl)
            out.append(f'<rect x="{x}" y="{gy + top}" width="10" height="{bot - top}" rx="1.5" '
                       + (f'fill="{col}"' if cl < o else f'fill="none" {s}') + "/>")
        if label:
            out.append(T(gx + 120, gy + 118, label.upper(), "monob", 7.5, col, 1, "end"))
        return "".join(out)
    if kind == "room":
        p = lambda pts: " ".join(f"{gx + x},{gy + y}" for x, y in pts)
        return f"""<polygon points="{p([(20, 10), (100, 10), (100, 78), (20, 78)])}" {s}/>
<polyline points="{p([(0, 116), (20, 78)])}" {s}/><polyline points="{p([(120, 116), (100, 78)])}" {s}/>
<polyline points="{p([(0, 0), (20, 10)])}" {s}/><polyline points="{p([(120, 0), (100, 10)])}" {s}/>
<rect x="{gx + 38}" y="{gy + 24}" width="44" height="28" rx="2" fill="{col}"/>
<line x1="{gx + 60}" y1="{gy + 52}" x2="{gx + 60}" y2="{gy + 60}" {s}/><line x1="{gx + 50}" y1="{gy + 60}" x2="{gx + 70}" y2="{gy + 60}" {s}/>
<rect x="{gx + 30}" y="{gy + 88}" width="60" height="18" rx="5" {s}/><rect x="{gx + 26}" y="{gy + 84}" width="10" height="24" rx="4" {s}/><rect x="{gx + 84}" y="{gy + 84}" width="10" height="24" rx="4" {s}/>
<circle cx="{gx + 60}" cy="{gy + 0}" r="3" fill="{col}"/><line x1="{gx + 60}" y1="{gy + 3}" x2="{gx + 60}" y2="{gy + 10}" {s} stroke-dasharray="1 2"/>"""
    if kind == "sword":
        wraps = "".join(f'<line x1="{gx + 18 + k * 5}" y1="{gy + 94 - k * 5}" x2="{gx + 26 + k * 5}" y2="{gy + 102 - k * 5}" {s}/>' for k in range(4))
        return f"""<path d="M{gx + 96} {gy + 14} A44 44 0 1 0 {gx + 112} {gy + 58} A34 34 0 1 1 {gx + 96} {gy + 14}Z" fill="{col}" opacity=".9"/>
<path d="M{gx + 44} {gy + 70} L{gx + 104} {gy + 8} Q{gx + 108} {gy + 6} {gx + 106} {gy + 12} L{gx + 50} {gy + 76}Z" {s}/>
<line x1="{gx + 12}" y1="{gy + 110}" x2="{gx + 40}" y2="{gy + 82}" stroke="{col}" stroke-width="7" stroke-linecap="round"/>
<ellipse cx="{gx + 45}" cy="{gy + 76}" rx="11" ry="5" transform="rotate(-45 {gx + 45} {gy + 76})" fill="{col}"/>
{wraps}"""
    if kind == "browser":
        out = [f'<rect x="{gx}" y="{gy + 6}" width="120" height="104" rx="7" {s}/>',
               f'<line x1="{gx}" y1="{gy + 26}" x2="{gx + 120}" y2="{gy + 26}" {s}/>']
        out += [f'<circle cx="{gx + 12 + k * 10}" cy="{gy + 16}" r="3" fill="{col}"/>' for k in range(3)]
        for k, ok in enumerate([True, True, False, True]):
            y = gy + 44 + k * 18
            out.append(f'<path d="M{gx + 12} {y} l4 4 l8 -8" {s}/>' if ok else
                       f'<path d="M{gx + 13} {y - 4} l8 8 m0 -8 l-8 8" {s}/>')
            out.append(f'<rect x="{gx + 32}" y="{y - 3}" width="{70 - k * 9}" height="6" rx="3" fill="{col}" opacity="{1 if ok else .35}"/>')
        return "".join(out)

    # space tech
    if kind == "rocket":
        stars = "".join(sparkle(gx + x, gy + y, r, col) for x, y, r in [(14, 22, 5), (104, 96, 4), (22, 92, 3)])
        return f"""{stars}<g transform="rotate(32 {gx + 60} {gy + 60}) translate({gx + 60} {gy + 58}) scale(1.14) translate({-gx - 60} {-gy - 58})">
<path d="M{gx + 60} {gy + 2} C{gx + 73} {gy + 16} {gx + 77} {gy + 38} {gx + 74} {gy + 74} H{gx + 46} C{gx + 43} {gy + 38} {gx + 47} {gy + 16} {gx + 60} {gy + 2}Z" {s}/>
<circle cx="{gx + 60}" cy="{gy + 36}" r="7" {s}/>
<path d="M{gx + 46} {gy + 54} L{gx + 32} {gy + 80} L{gx + 46} {gy + 76}Z M{gx + 74} {gy + 54} L{gx + 88} {gy + 80} L{gx + 74} {gy + 76}Z" fill="{col}"/>
<path d="M{gx + 50} {gy + 78} Q{gx + 60} {gy + 120} {gx + 70} {gy + 78}Z" fill="{col}"/>
<path d="M{gx + 50} {gy + 116} v6 M{gx + 60} {gy + 120} v8 M{gx + 70} {gy + 116} v6" {s} stroke-dasharray="2 3"/></g>"""
    if kind == "satellite":
        panel = lambda x: (f'<rect x="{gx + x}" y="{gy + 52}" width="36" height="18" rx="2" {s}/>'
                           + "".join(f'<line x1="{gx + x + 9 * k}" y1="{gy + 52}" x2="{gx + x + 9 * k}" y2="{gy + 70}" {s}/>' for k in (1, 2, 3)))
        waves = "".join(f'<path d="M{gx + 76 + r * .7:.1f} {gy + 22 - r * .7:.1f} A{r} {r} 0 0 1 {gx + 76 + r:.1f} {gy + 22:.1f}" {s} opacity="{o}"/>'
                        for r, o in [(12, 1), (22, .6), (32, .3)])
        return f"""<g transform="rotate(-18 {gx + 60} {gy + 60})">{panel(4)}{panel(80)}
<line x1="{gx + 40}" y1="{gy + 61}" x2="{gx + 48}" y2="{gy + 61}" {s}/><line x1="{gx + 72}" y1="{gy + 61}" x2="{gx + 80}" y2="{gy + 61}" {s}/>
<rect x="{gx + 48}" y="{gy + 48}" width="24" height="26" rx="3" fill="{col}"/>
<line x1="{gx + 60}" y1="{gy + 48}" x2="{gx + 60}" y2="{gy + 36}" {s}/>
<path d="M{gx + 45} {gy + 26} Q{gx + 60} {gy + 48} {gx + 75} {gy + 26}Z" fill="{col}"/><line x1="{gx + 60}" y1="{gy + 32}" x2="{gx + 60}" y2="{gy + 18}" {s}/><circle cx="{gx + 60}" cy="{gy + 17}" r="2.5" fill="{col}"/>
<path d="M{gx + 52} {gy + 74} l-4 10 h24 l-4 -10" {s}/></g>{waves}"""
    if kind == "rover":
        wheels = "".join(f'<circle cx="{gx + x}" cy="{gy + 94}" r="10" {s}/><circle cx="{gx + x}" cy="{gy + 94}" r="3" fill="{col}"/>' for x in (24, 60, 96))
        return f"""<line x1="{gx}" y1="{gy + 105}" x2="{gx + 120}" y2="{gy + 105}" {s} stroke-dasharray="2 4"/>
<rect x="{gx + 22}" y="{gy + 50}" width="70" height="22" rx="4" {s}/>
<rect x="{gx + 26}" y="{gy + 42}" width="44" height="6" rx="1.5" fill="{col}"/>
<polyline points="{gx + 24},{gy + 94} {gx + 40},{gy + 76} {gx + 60},{gy + 94}" {s} fill="none"/>
<polyline points="{gx + 40},{gy + 76} {gx + 78},{gy + 76} {gx + 96},{gy + 94}" {s} fill="none"/>
<line x1="{gx + 82}" y1="{gy + 50}" x2="{gx + 82}" y2="{gy + 24}" {s}/>
<rect x="{gx + 72}" y="{gy + 12}" width="26" height="13" rx="3" fill="{col}"/><circle cx="{gx + 92}" cy="{gy + 18.5}" r="2.5" fill="none" stroke="{col}"/>
<path d="M{gx + 100} {gy + 16} l14 -6 M{gx + 100} {gy + 21} l14 2" {s} stroke-dasharray="2 3"/>{wheels}"""

    # robotics
    if kind == "arm":
        return f"""<line x1="{gx}" y1="{gy + 116}" x2="{gx + 120}" y2="{gy + 116}" {s}/>
<path d="M{gx + 14} {gy + 116} L{gx + 20} {gy + 100} H{gx + 48} L{gx + 54} {gy + 116}" {s}/>
<line x1="{gx + 34}" y1="{gy + 98}" x2="{gx + 26}" y2="{gy + 52}" stroke="{col}" stroke-width="8" stroke-linecap="round"/>
<line x1="{gx + 26}" y1="{gy + 52}" x2="{gx + 78}" y2="{gy + 30}" stroke="{col}" stroke-width="6" stroke-linecap="round"/>
<circle cx="{gx + 34}" cy="{gy + 98}" r="7" fill="{col}"/><circle cx="{gx + 26}" cy="{gy + 52}" r="9" {s}/><circle cx="{gx + 78}" cy="{gy + 30}" r="6" {s}/>
<path d="M{gx + 84} {gy + 30} l8 2 v14 M{gx + 84} {gy + 30} l14 -6 l6 10" {s}/>
<rect x="{gx + 90}" y="{gy + 50}" width="20" height="20" rx="2" fill="{col}"/>
<path d="M{gx + 100} {gy + 76} V{gy + 104} H{gx + 70}" {s} stroke-dasharray="2 4"/>
<rect x="{gx + 60}" y="{gy + 98}" width="10" height="10" rx="1.5" {s}/>"""
    if kind == "drone":
        rotors = "".join(f'<line x1="{gx + 60}" y1="{gy + 58}" x2="{gx + x}" y2="{gy + y}" stroke="{col}" stroke-width="3" stroke-linecap="round"/>'
                         f'<ellipse cx="{gx + x}" cy="{gy + y - 4}" rx="18" ry="4.5" {s}/><circle cx="{gx + x}" cy="{gy + y - 4}" r="2.5" fill="{col}"/>'
                         for x, y in [(18, 34), (102, 34), (30, 70), (90, 70)])
        return f"""{rotors}<rect x="{gx + 46}" y="{gy + 48}" width="28" height="20" rx="6" fill="{col}"/>
<circle cx="{gx + 60}" cy="{gy + 74}" r="4" {s}/>
<path d="M{gx + 52} {gy + 84} L{gx + 38} {gy + 116} M{gx + 60} {gy + 84} V{gy + 118} M{gx + 68} {gy + 84} L{gx + 82} {gy + 116}" {s} stroke-dasharray="2 4"/>"""

    # agrotech
    if kind == "sprout":
        soil = "".join(f'<circle cx="{gx + x}" cy="{gy + y}" r="1.6" fill="{col}"/>' for x, y in [(10, 112), (28, 116), (46, 111), (70, 115), (88, 112), (112, 116)])
        waves = "".join(f'<path d="M{gx + 101 - r} {gy + 58 - r * .6:.1f} Q{gx + 101} {gy + 58 - r * 1.3:.1f} {gx + 101 + r} {gy + 58 - r * .6:.1f}" {s} opacity="{o}"/>'
                        for r, o in [(6, 1), (11, .6), (16, .3)])
        return f"""<path d="M{gx} {gy + 104} Q{gx + 40} {gy + 96} {gx + 60} {gy + 100} T{gx + 120} {gy + 104}" {s}/>{soil}
<path d="M{gx + 52} {gy + 100} C{gx + 52} {gy + 84} {gx + 48} {gy + 70} {gx + 52} {gy + 52}" {s}/>
<path d="M{gx + 51} {gy + 70} C{gx + 32} {gy + 68} {gx + 18} {gy + 54} {gx + 18} {gy + 36} C{gx + 36} {gy + 38} {gx + 50} {gy + 52} {gx + 51} {gy + 70}Z" fill="{col}"/>
<path d="M{gx + 52} {gy + 56} C{gx + 66} {gy + 52} {gx + 78} {gy + 38} {gx + 78} {gy + 20} C{gx + 62} {gy + 22} {gx + 52} {gy + 36} {gx + 52} {gy + 56}Z" {s}/>
<path d="M{gx + 53} {gy + 54} L{gx + 70} {gy + 30}" {s}/>
<line x1="{gx + 101}" y1="{gy + 112}" x2="{gx + 101}" y2="{gy + 72}" {s}/><rect x="{gx + 94}" y="{gy + 62}" width="14" height="10" rx="2" fill="{col}"/>{waves}"""
    if kind == "field":
        rows = []
        for k in range(7):
            bx = k * 20
            tx_ = 60 + (bx - 60) * .2
            rows.append(f'<line x1="{gx + bx}" y1="{gy + 118}" x2="{gx + tx_:.1f}" y2="{gy + 50}" {s} stroke-dasharray="{"3 3" if k % 2 else "1 4"}"/>')
            for j, t in enumerate((.15, .45)):
                x, y = bx + (tx_ - bx) * t, 118 - 68 * t
                r = 5 - j * 2
                rows.append(f'<path d="M{gx + x - r:.1f} {gy + y - r:.1f} L{gx + x:.1f} {gy + y:.1f} L{gx + x + r:.1f} {gy + y - r:.1f}" {s}/>')
        rays = "".join(f'<line x1="{gx + 92 + 15 * math.cos(math.radians(a)):.1f}" y1="{gy + 20 + 15 * math.sin(math.radians(a)):.1f}" '
                       f'x2="{gx + 92 + 21 * math.cos(math.radians(a)):.1f}" y2="{gy + 20 + 21 * math.sin(math.radians(a)):.1f}" {s}/>' for a in range(0, 360, 45))
        return f"""<line x1="{gx}" y1="{gy + 50}" x2="{gx + 120}" y2="{gy + 50}" {s}/>{"".join(rows)}
<circle cx="{gx + 92}" cy="{gy + 20}" r="10" fill="{col}"/>{rays}
<path d="M{gx + 10} {gy + 30} q6 -6 12 0 q6 -6 12 0" {s}/>"""
    return ""


def card(idx, p, side, status, dot):
    """side: 'l', 'r' or 'f' (full width). Half cards carry half the gutter so two 50% images tile flush."""
    w, h = (W if side == "f" else 480), 344
    x0 = GAP / 2 + 0.5 if side == "r" else 0.5
    x1 = w - GAP / 2 - 0.5 if side == "l" else w - 0.5
    cw = x1 - x0
    bottom = h - GAP - 0.5
    name, desc, tags, kind = p["name"], p["description"], p.get("tags", []), p["drawing"]
    stock = COLOURS[p["colour"]]
    fill = STOCK[stock]
    txt = CREAM if stock in ("ultra", "ink") else INK
    px = x0 + 28
    out = []
    out.append(T(x1 + 18, bottom + 64, f"{idx:02d}", "anton", 270, txt, 0, "end", ' opacity=".09"'))
    out.append(T(px, 46, f"№ {idx:02d}", "monob", 12, txt, 2))
    sx = px + tw(f"№ {idx:02d}", "monob", 12, 2) + 12
    sw = tw(status, "monob", 9.5, 1.4) + 20
    out.append(f'<rect x="{sx}" y="31" width="{sw + (10 if dot else 0)}" height="22" rx="11" stroke="{txt}" stroke-opacity=".55"/>')
    if dot:
        out.append(f'<circle class="live" cx="{sx + 13}" cy="42" r="3.5" fill="{txt}"/>')
    out.append(T(sx + 10 + (10 if dot else 0), 45.5, status, "monob", 9.5, txt, 1.4))
    ax, ay = x1 - 46, 42
    out.append(f'<circle cx="{ax}" cy="{ay}" r="18" stroke="{txt}" stroke-width="1.4"/>')
    out.append(f'<path d="M{ax - 6} {ay + 6} L{ax + 6} {ay - 6} M{ax - 3} {ay - 6} H{ax + 6} V{ay + 3}" stroke="{txt}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>')

    if side == "f":  # room to spare, so the drawing gets bigger and the rule stops short of it
        gs = 1.75
        out.append(f'<g transform="translate({x1 - 140 - 120 * gs:.1f} 70) scale({gs})">{glyph(kind, 0, 0, txt, p.get("drawing_label", ""))}</g>')
        rule_end = px + 500
    else:
        out.append(glyph(kind, x1 - 28 - 120, 74, txt, p.get("drawing_label", "")))
        rule_end = x1 - 28
    ns = fit(name, "serif", 56, cw - 56 - 140, -1)
    out.append(T(px - 2, 148, name, "serif", ns, txt, -1))

    out.append(f'<line x1="{px}" y1="{198.5}" x2="{rule_end}" y2="{198.5}" stroke="{txt}" stroke-opacity=".5" stroke-dasharray="2 4"/>')
    for i, line in enumerate(wrap_px(desc, "serif", 19.5, min(cw - 56, 500))[:3]):
        out.append(T(px, 228 + i * 23.5, line, "serif", 19.5, txt))

    tx = px
    for t in tags:
        s = t.upper()
        tw_ = tw(s, "monob", 9.5, 1.3) + 20
        out.append(f'<rect x="{tx}" y="{bottom - 46}" width="{tw_:.1f}" height="24" rx="12" fill="{txt}" fill-opacity=".1" stroke="{txt}" stroke-opacity=".45"/>')
        out.append(T(tx + 10, bottom - 30, s, "monob", 9.5, txt, 1.3))
        tx += tw_ + 8

    c = dict(grain=.12, border=fill)
    css = """.live { animation: blink 1.6s ease-in-out infinite alternate; } @keyframes blink { from { opacity: .25; } }"""
    return panel(c, w, h, "\n".join(out), fill=fill, css=css, rect=(x0, 0.5, cw, bottom - 0.5), rx=20, stroke=fill)


# ── tools ────────────────────────────────────────────────────────────────────

def tools(c):
    tc = CONTENT["tools"]
    groups = tc["groups"]
    rh, top = 92, 20
    H = top + rh * len(groups) + 18
    out = []
    for i, g in enumerate(groups):
        label, accent, items = g["label"], COLOURS[g["colour"]], [str(x) for x in g["items"]]
        y = top + i * rh
        base = y + 58
        out.append(T(36, y + 36, label.upper(), "anton", fit(label.upper(), "anton", 26, 160, 1.5), c[accent], 1.5))
        out.append(T(36, y + 58, fill(tc["count"], count=f"{len(items):02d}").upper(), "monob", 9.5, c["muted"], 1.6))
        size = 44
        while True:
            total = sum(tw(t, "ital", size) for t in items) + 34 * (len(items) - 1)
            if total < W - 36 - 230 or size < 20:
                break
            size -= 1
        x = 230
        for k, t in enumerate(items):
            out.append(T(x, base, t, "ital" if k % 2 else "serif", size, c["ink"]))
            x += tw(t, "ital" if k % 2 else "serif", size)
            if k < len(items) - 1:
                out.append(sparkle(x + 17, base - size * .3, 6.5, c[accent]))
                x += 34
        if i < len(groups) - 1:
            out.append(f'<line x1="36" y1="{y + rh}" x2="{W - 36}" y2="{y + rh}" stroke="{c["line"]}" stroke-dasharray="2 5"/>')
    out.append(f'<line x1="206" y1="{top + 10}" x2="206" y2="{H - 26}" stroke="{c["line"]}"/>')
    return panel(c, W, H, "\n".join(out))


# ── footer ───────────────────────────────────────────────────────────────────

def footer(c):
    H = 330
    cx, cy = W - 112, 92
    out = []
    t = CONTENT["footer"]
    big = t["big"].upper()
    out.append(T(30, 190, big, "anton", fit(big, "anton", 172, W - 250, 2), c["ink"], 2))
    out.append(T(W - 36, 292, t["sign_off"], "ital", fit(t["sign_off"], "ital", 150, W - 330, -3), c["verm"], -3, "end"))
    out.append(f"""<circle cx="{cx}" cy="{cy}" r="46" stroke="{c['line']}"/>
<circle cx="{cx}" cy="{cy}" r="28" stroke="{c['muted']}" stroke-dasharray="1 5" stroke-linecap="round"/>
<circle cx="{cx}" cy="{cy}" r="9" fill="{c['mari']}"/>
<g class="orbit"><circle cx="{cx + 46}" cy="{cy}" r="5" fill="{c['ink']}"/></g>
<g class="orbit2"><circle cx="{cx}" cy="{cy - 28}" r="3" fill="{c['verm']}"/></g>""")
    for i, line in enumerate(t["colophon"][:3]):
        out.append(T(36, 248 + i * 16, line.upper(), "mono", 9.5, c["muted"], 1.4))
    out.append(sparkle(36 + 6, 222, 6, c["mari"]))
    css = f"""
  .orbit {{ transform-origin: {cx}px {cy}px; animation: spin 20s linear infinite; }}
  .orbit2 {{ transform-origin: {cx}px {cy}px; animation: spin 8s linear infinite reverse; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}"""
    return panel(c, W, H, "\n".join(out), css=css)


def pic(name, alt):
    """A themed full-width image: dark and light variants behind one <picture>."""
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
            f'<img alt="{escape(alt, {chr(34): "&quot;"})}" src="assets/{name}-light.svg" width="100%"></picture>')


def main():
    cal = fetch_calendar()
    h, t, f = CONTENT["header"], CONTENT["tools"], CONTENT["footer"]
    keep = set()

    def write(name, text):
        (OUT / name).write_text(text)
        keep.add(name)

    readme = [pic("header", f"{h['first_name']} {h['last_name']}. {h['tagline']} {h['intro']}"),
              pic("activity", CONTENT["activity"]["alt"])]
    heads = [(sec["title"], sec.get("kicker", ""), sec.get("subtitle", "")) for sec in CONTENT["sections"]]
    heads.append((t["title"], t.get("kicker", ""), t.get("subtitle", "")))
    for theme, c in THEMES.items():
        for name, fn in {"header": header, "tools": tools, "footer": footer}.items():
            write(f"{name}-{theme}.svg", fn(c))
        write(f"activity-{theme}.svg", activity(c, cal))
        for i, (title, kicker, sub) in enumerate(heads, 2):
            write(f"section-{slug(title)}-{theme}.svg", section(c, f"{i:02d}", title, kicker, sub))

    # cards use fixed stock colours, so one file serves both themes
    n = 0
    for i, sec in enumerate(CONTENT["sections"]):
        readme.append(pic(f"section-{slug(sec['title'])}", f"{i + 2:02d} {sec['title']}"))
        links = []
        items = sec["projects"]
        for k, p in enumerate(items):
            n += 1
            side = "f" if k == len(items) - 1 and k % 2 == 0 else "lr"[k % 2]
            write(f"card-{slug(p['name'])}.svg", card(n, p, side, sec["status"].upper(), sec.get("status_dot", False)))
            alt = escape(f"{p['name']}: {p['description']}", {chr(34): "&quot;"})
            links.append(("<br>" if k and k % 2 == 0 else "")
                         + f'<a href="https://github.com/{USER}/{p["repo"]}"><img alt="{alt}" '
                         f'src="assets/card-{slug(p["name"])}.svg" width="{"100%" if side == "f" else "50%"}"></a>')
        readme.append("<p>\n" + "".join(links) + "\n</p>")

    readme.append(pic(f"section-{slug(t['title'])}", f"{len(heads) + 1:02d} {t['title']}"))
    readme.append(pic("tools", " · ".join(", ".join(map(str, g["items"])) for g in t["groups"])))
    readme.append("<br>")
    readme.append(pic("footer", f"{f['big']} {f['sign_off']}"))
    (ROOT / "README.md").write_text("<!-- generated by assets/build.py from content.yml; edit that instead -->\n\n"
                                    + "\n\n".join(readme) + "\n")

    # drop images for projects or sections that were removed from content.yml
    for old in list(OUT.glob("card-*.svg")) + list(OUT.glob("section-*.svg")):
        if old.name not in keep:
            old.unlink()


if __name__ == "__main__":
    main()
