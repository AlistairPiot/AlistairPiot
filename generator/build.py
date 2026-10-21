#!/usr/bin/env python3
"""Generate the animated SVG assets of the GitHub profile README.

GitHub renders README images as <img>, so no JavaScript runs: every effect here
is pure SVG (SMIL + CSS keyframes). The "3D" objects are projected in Python and
baked into keyframes. Live data (contributions, repos) is fetched at build time;
the GitHub Action re-runs this script daily so the profile stays alive.

Stdlib only. Usage: python3 generator/build.py
"""

import datetime as dt
import html
import json
import math
import os
import random
import re
import urllib.request
from pathlib import Path

USER = "AlistairPiot"
OUT = Path(__file__).resolve().parent.parent / "assets"

SANS = "'Segoe UI', 'SF Pro Display', -apple-system, 'Helvetica Neue', Ubuntu, Arial, sans-serif"
MONO = "'JetBrains Mono', 'Fira Code', 'SFMono-Regular', ui-monospace, Menlo, Consolas, 'DejaVu Sans Mono', monospace"

BG = "#04050d"
CYAN = "#00f0ff"
MAGENTA = "#ff2bd6"
VIOLET = "#7c3aed"
LIME = "#b6ff3b"
AMBER = "#ffb020"

PROJECTS = [
    {
        "slug": "payo365",
        "name": "Payo365",
        "url": "https://payo365.com",
        "lines": ["La solution ultra-simple pour freelances", "et créateurs. Générez un lien, partagez-le", "et encaissez instantanément."],
        "tags": [("Next.js", "#e6e6e6"), ("Stripe", "#8d84ff")],
        "status": "LIVE",
        "glyph": "pay",
        "accent": LIME,
    },
    {
        "slug": "neontwin",
        "name": "NeonTwin",
        "url": None,
        "lines": ["Votre jumeau numérique stratégique : une IA", "qui mémorise tout, détecte vos angles morts", "et vous conseille comme un associé senior."],
        "tags": [("Next.js", "#e6e6e6"), ("IA", "#b28cff")],
        "status": "IN DEV",
        "glyph": "twin",
        "accent": MAGENTA,
    },
    {
        "slug": "vasy",
        "name": "Vasy",
        "url": None,
        "lines": ["La plateforme des créateurs français.", "Des produits artisanaux uniques, créés", "par des artisans passionnés."],
        "tags": [("Next.js", "#e6e6e6"), ("Tailwind", "#38bdf8")],
        "status": "IN DEV",
        "glyph": "vasy",
        "accent": CYAN,
    },
]

STACK_RINGS = [
    ("FRONTEND", CYAN, ["Next.js", "React", "TypeScript", "Tailwind", "shadcn/ui"]),
    ("BACKEND", MAGENTA, ["Node.js", "Prisma", "PostgreSQL", "Supabase", "REST API"]),
    ("TOOLING", LIME, ["Vercel", "Stripe", "Figma", "Git", "Notion"]),
]


def f(x):
    """Compact number formatting for SVG attributes."""
    s = f"{x:.1f}"
    return s[:-2] if s.endswith(".0") else s


def svg(w, h, body, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{html.escape(title)}"><title>{html.escape(title)}</title>{body}</svg>\n'
    )


def write(name, content):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"  {name:28s} {len(content.encode()) / 1024:7.1f} KB")


# --------------------------------------------------------------------------- data

def http_get(url, token=None, data=None):
    headers = {"User-Agent": f"{USER}-profile-generator"}
    if token:
        headers["Authorization"] = f"bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def fetch_contributions():
    """Return a list of weeks, each a list of (date, count, level). Tries GraphQL, then the public calendar page."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        try:
            q = {"query": 'query{user(login:"%s"){contributionsCollection{contributionCalendar{weeks{contributionDays{date contributionCount contributionLevel}}}}}}' % USER}
            raw = json.loads(http_get("https://api.github.com/graphql", token, json.dumps(q).encode()))
            levels = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
            weeks = raw["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
            return [[(d["date"], d["contributionCount"], levels[d["contributionLevel"]]) for d in w["contributionDays"]] for w in weeks]
        except Exception as e:  # noqa: BLE001 - fall back to scraping
            print(f"  graphql failed ({e}), falling back to public calendar")
    try:
        page = http_get(f"https://github.com/users/{USER}/contributions")
        tips = {m[0]: m[1] for m in re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)</tool-tip>', page)}
        cells = {}
        for date, cid, level in re.findall(r'data-date="([^"]+)"\s+id="([^"]+)"\s+data-level="(\d)"', page):
            m = re.match(r"([\d,]+) contribution", tips.get(cid, ""))
            cells[date] = (int(m.group(1).replace(",", "")) if m else 0, int(level))
        dates = sorted(cells)
        if not dates:
            raise ValueError("empty calendar")
        weeks, cur = [], []
        for d in dates:
            day = dt.date.fromisoformat(d)
            if day.weekday() == 6 and cur:  # weeks start on Sunday
                weeks.append(cur)
                cur = []
            cur.append((d, *cells[d]))
        weeks.append(cur)
        return weeks
    except Exception as e:  # noqa: BLE001 - offline build still produces a profile
        print(f"  calendar scrape failed ({e}), using synthetic data")
        rnd = random.Random(7)
        start = dt.date.today() - dt.timedelta(days=364)
        start -= dt.timedelta(days=(start.weekday() + 1) % 7)
        weeks = []
        for w in range(53):
            week = []
            for d in range(7):
                c = max(0, int(rnd.gauss(2, 4)))
                week.append(((start + dt.timedelta(days=w * 7 + d)).isoformat(), c, min(4, (c + 2) // 3)))
            weeks.append(week)
        return weeks


def fetch_repos():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        repos = json.loads(http_get(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner", token))
        return [r for r in repos if not r.get("fork")]
    except Exception as e:  # noqa: BLE001
        print(f"  repos fetch failed ({e})")
        return []


def contribution_stats(weeks):
    days = [d for w in weeks for d in w]
    total = sum(c for _, c, _ in days)
    best = max(days, key=lambda d: d[1]) if days else ("", 0, 0)
    longest = run = 0
    for _, c, _ in days:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current = 0
    for i, (_, c, _) in enumerate(reversed(days)):
        if c:
            current += 1
        elif i > 0:  # today without commits does not break the streak yet
            break
    active = sum(1 for _, c, _ in days if c)
    return {"total": total, "best": best, "longest": longest, "current": current, "active": active}


# --------------------------------------------------------------------------- 3D helpers

def rot(p, ax, ay, az=0.0):
    x, y, z = p
    cy, sy = math.cos(ay), math.sin(ay)
    x, z = x * cy + z * sy, -x * sy + z * cy
    cx, sx = math.cos(ax), math.sin(ax)
    y, z = y * cx - z * sx, y * sx + z * cx
    if az:
        cz, sz = math.cos(az), math.sin(az)
        x, y = x * cz - y * sz, x * sz + y * cz
    return x, y, z


def project(p, cx, cy, scale, cam=4.2):
    x, y, z = p
    k = cam / (cam - z)
    return cx + x * scale * k, cy + y * scale * k, z


def icosphere(subdiv):
    t = (1 + 5 ** 0.5) / 2
    verts = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t),
             (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    verts = [tuple(c / math.sqrt(sum(v * v for v in p)) for c in p) for p in verts]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
             (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
             (8, 6, 7), (9, 8, 1)]
    for _ in range(subdiv):
        cache, nf = {}, []

        def mid(a, b):
            key = (min(a, b), max(a, b))
            if key not in cache:
                p = [(verts[a][i] + verts[b][i]) / 2 for i in range(3)]
                n = math.sqrt(sum(c * c for c in p))
                verts.append(tuple(c / n for c in p))
                cache[key] = len(verts) - 1
            return cache[key]

        for a, b, c in faces:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = nf
    edges = sorted({(min(a, b), max(a, b)) for fc in faces for a, b in ((fc[0], fc[1]), (fc[1], fc[2]), (fc[2], fc[0]))})
    return verts, edges


def wireframe(verts, edges, cx, cy, scale, frames, dur, color, tilt, direction=1, width=1.2, dots=True, spin_offset=0.0):
    """Bake a rotating wireframe into per-edge SMIL keyframes, with depth-based opacity."""
    proj = []
    for i in range(frames + 1):
        a = direction * 2 * math.pi * i / frames + spin_offset
        proj.append([project(rot(v, tilt, a, 0.25), cx, cy, scale) for v in verts])
    out = []
    common = f'dur="{dur}s" repeatCount="indefinite" calcMode="linear"'
    for a, b in edges:
        xs1 = ";".join(f(fr[a][0]) for fr in proj)
        ys1 = ";".join(f(fr[a][1]) for fr in proj)
        xs2 = ";".join(f(fr[b][0]) for fr in proj)
        ys2 = ";".join(f(fr[b][1]) for fr in proj)
        op = ";".join(f"{0.12 + 0.88 * ((fr[a][2] + fr[b][2]) / 2 + 1) / 2:.2f}" for fr in proj)
        p0a, p0b = proj[0][a], proj[0][b]
        out.append(
            f'<line x1="{f(p0a[0])}" y1="{f(p0a[1])}" x2="{f(p0b[0])}" y2="{f(p0b[1])}" stroke="{color}" stroke-width="{width}">'
            f'<animate attributeName="x1" values="{xs1}" {common}/><animate attributeName="y1" values="{ys1}" {common}/>'
            f'<animate attributeName="x2" values="{xs2}" {common}/><animate attributeName="y2" values="{ys2}" {common}/>'
            f'<animate attributeName="stroke-opacity" values="{op}" {common}/></line>'
        )
    if dots:
        for i in range(len(verts)):
            xs = ";".join(f(fr[i][0]) for fr in proj)
            ys = ";".join(f(fr[i][1]) for fr in proj)
            rs = ";".join(f"{1.2 + 1.6 * (fr[i][2] + 1) / 2:.2f}" for fr in proj)
            out.append(
                f'<circle cx="{f(proj[0][i][0])}" cy="{f(proj[0][i][1])}" r="2" fill="#fff">'
                f'<animate attributeName="cx" values="{xs}" {common}/><animate attributeName="cy" values="{ys}" {common}/>'
                f'<animate attributeName="r" values="{rs}" {common}/></circle>'
            )
    return "".join(out)


# --------------------------------------------------------------------------- shared pieces

def stars(rnd, n, w, h, ymax=None):
    out = []
    for _ in range(n):
        x, y = rnd.uniform(0, w), rnd.uniform(0, ymax or h)
        r = rnd.choice([0.6, 0.8, 1, 1.3])
        d = rnd.uniform(2, 6)
        out.append(
            f'<circle cx="{f(x)}" cy="{f(y)}" r="{r}" fill="#fff" opacity="0.2">'
            f'<animate attributeName="opacity" values="0.15;{rnd.uniform(0.6, 1):.2f};0.15" dur="{d:.1f}s" '
            f'begin="-{rnd.uniform(0, d):.1f}s" repeatCount="indefinite"/></circle>'
        )
    return "".join(out)


def hud_corners(x, y, w, h, size=18, color=CYAN, opacity=0.7):
    s = size
    path = (f"M{x} {y + s}V{y}H{x + s}M{x + w - s} {y}H{x + w}V{y + s}"
            f"M{x + w} {y + h - s}V{y + h}H{x + w - s}M{x + s} {y + h}H{x}V{y + h - s}")
    return f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2" opacity="{opacity}"/>'


def scanlines(id_, w, h):
    return (f'<defs><pattern id="{id_}" width="4" height="4" patternUnits="userSpaceOnUse">'
            f'<rect width="4" height="1" fill="#fff" opacity="0.035"/></pattern></defs>'
            f'<rect width="{w}" height="{h}" fill="url(#{id_})" pointer-events="none"/>')


def scan_beam(id_, w, h, dur=6):
    return (f'<defs><linearGradient id="{id_}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{CYAN}" stop-opacity="0"/>'
            f'<stop offset="0.85" stop-color="{CYAN}" stop-opacity="0.07"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0.35"/></linearGradient></defs>'
            f'<rect x="0" y="-120" width="{w}" height="120" fill="url(#{id_})">'
            f'<animate attributeName="y" values="-120;{h}" dur="{dur}s" repeatCount="indefinite"/></rect>')


def intro(delay, dur=0.9):
    """SMIL fade-up whose base value stays visible, so content shows even where animation is disabled."""
    k = delay / (delay + dur)
    return (f'<animate attributeName="opacity" values="0;0;1" keyTimes="0;{k:.3f};1" dur="{delay + dur:.2f}s" fill="freeze"/>'
            f'<animateTransform attributeName="transform" type="translate" values="0 14;0 14;0 0" keyTimes="0;{k:.3f};1" '
            f'dur="{delay + dur:.2f}s" calcMode="spline" keySplines="0 0 1 1;.2 .8 .2 1" fill="freeze"/>')


# --------------------------------------------------------------------------- hero

def build_hero(stats, now):
    W, H = 1200, 520
    rnd = random.Random(42)
    hz = 352  # horizon
    vx = 860  # vanishing point x (under the hologram)

    defs = f"""<defs>
<radialGradient id="neb1" cx="0.72" cy="0.38" r="0.55"><stop offset="0" stop-color="{VIOLET}" stop-opacity="0.55"/><stop offset="0.5" stop-color="#2b0b5e" stop-opacity="0.25"/><stop offset="1" stop-color="{BG}" stop-opacity="0"/></radialGradient>
<radialGradient id="neb2" cx="0.12" cy="0.1" r="0.5"><stop offset="0" stop-color="#003a5c" stop-opacity="0.7"/><stop offset="1" stop-color="{BG}" stop-opacity="0"/></radialGradient>
<linearGradient id="floorFade" x1="0" y1="{hz}" x2="0" y2="{H}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.35" stop-color="#fff" stop-opacity="0.6"/><stop offset="1" stop-color="#fff" stop-opacity="1"/></linearGradient>
<mask id="floorMask"><rect x="0" y="{hz}" width="{W}" height="{H - hz}" fill="url(#floorFade)"/></mask>
<linearGradient id="horizon" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{MAGENTA}" stop-opacity="0"/><stop offset="0.5" stop-color="{MAGENTA}"/><stop offset="0.72" stop-color="{CYAN}"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></linearGradient>
<linearGradient id="beam" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{CYAN}" stop-opacity="0.55"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></linearGradient>
<radialGradient id="core" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#fff" stop-opacity="0.9"/><stop offset="0.25" stop-color="{CYAN}" stop-opacity="0.5"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></radialGradient>
<linearGradient id="holo" x1="0" y1="0" x2="1" y2="0" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{CYAN}"/><stop offset="0.33" stop-color="#ffffff"/><stop offset="0.66" stop-color="{MAGENTA}"/><stop offset="1" stop-color="{CYAN}"/>
<animateTransform attributeName="gradientTransform" type="translate" values="-700 0;700 0" dur="6s" repeatCount="indefinite"/></linearGradient>
<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<filter id="bigglow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="9"/></filter>
<clipPath id="sliceA"><rect x="0" y="150" width="{W}" height="14"><animate attributeName="y" values="150;178;132;196;150" dur="0.9s" repeatCount="indefinite"/></rect></clipPath>
<clipPath id="sliceB"><rect x="0" y="190" width="{W}" height="9"><animate attributeName="y" values="190;141;205;160;190" dur="0.7s" repeatCount="indefinite"/></rect></clipPath>
</defs>"""

    style = f"""<style>
.mono{{font-family:{MONO};}} .sans{{font-family:{SANS};}}
@keyframes blink{{0%,49%{{opacity:1}}50%,100%{{opacity:0}}}}
.cursor{{animation:blink 1s steps(1) infinite}}
@keyframes glitch{{0%,86%,100%{{opacity:0}}87%,89%,93%{{opacity:1}}88%,92%{{opacity:0.4}}}}
.glitch{{animation:glitch 5s infinite}}
@keyframes jitterA{{0%,86%,100%{{transform:translate(0,0)}}87%{{transform:translate(-9px,0)}}89%{{transform:translate(7px,0)}}93%{{transform:translate(-4px,0)}}}}
@keyframes jitterB{{0%,86%,100%{{transform:translate(0,0)}}87%{{transform:translate(11px,0)}}90%{{transform:translate(-6px,0)}}93%{{transform:translate(3px,0)}}}}
.jA{{animation:jitterA 5s infinite}} .jB{{animation:jitterB 5s infinite}}
@keyframes rgbL{{0%,100%{{transform:translate(-2px,0)}}50%{{transform:translate(-3.5px,0.5px)}}}}
@keyframes rgbR{{0%,100%{{transform:translate(2px,0)}}50%{{transform:translate(3.5px,-0.5px)}}}}
.rgbL{{animation:rgbL 3s ease-in-out infinite}} .rgbR{{animation:rgbR 3s ease-in-out infinite}}
@keyframes float{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-10px)}}}}
.float{{animation:float 6s ease-in-out infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
.pulse{{animation:pulse 1.6s ease-in-out infinite}}
@keyframes ring{{from{{r:5;opacity:.9}}to{{r:16;opacity:0}}}}
.ring{{animation:ring 1.6s ease-out infinite}}
</style>"""

    body = [defs, style, f'<rect width="{W}" height="{H}" rx="18" fill="{BG}"/>',
            f'<rect width="{W}" height="{H}" rx="18" fill="url(#neb2)"/><rect width="{W}" height="{H}" rx="18" fill="url(#neb1)"/>',
            stars(rnd, 90, W, H, hz - 10)]

    # --- perspective floor
    floor = []
    for i in range(-26, 27):
        x_bottom = vx + i * 70
        floor.append(f'<line x1="{vx}" y1="{hz}" x2="{x_bottom}" y2="{H + 160}"/>')
    n, dur = 12, 3.2
    samples = 24
    for i in range(n):
        ys = ";".join(f(hz + (H + 40 - hz) * (s / samples) ** 2.6) for s in range(samples + 1))
        floor.append(f'<line x1="0" y1="{hz}" x2="{W}" y2="{hz}"><animate attributeName="y1" values="{ys}" dur="{dur}s" begin="-{dur * i / n:.2f}s" repeatCount="indefinite"/>'
                     f'<animate attributeName="y2" values="{ys}" dur="{dur}s" begin="-{dur * i / n:.2f}s" repeatCount="indefinite"/></line>')
    body.append(f'<g mask="url(#floorMask)" stroke="{MAGENTA}" stroke-opacity="0.55" stroke-width="1.2">{"".join(floor)}</g>')
    body.append(f'<rect x="0" y="{hz - 1}" width="{W}" height="2" fill="url(#horizon)" filter="url(#glow)"/>')

    # --- hologram: projector beam + geodesic sphere + inner icosahedron + orbit ring
    hx, hy = vx, 196
    body.append(f'<path d="M{hx - 26} {hz + 40}L{hx - 150} {hy}A150 34 0 0 0 {hx + 150} {hy}L{hx + 26} {hz + 40}Z" fill="url(#beam)" opacity="0.35"><animate attributeName="opacity" values="0.25;0.45;0.3;0.4;0.25" dur="2.3s" repeatCount="indefinite"/></path>')
    body.append(f'<ellipse cx="{hx}" cy="{hz + 40}" rx="70" ry="12" fill="none" stroke="{CYAN}" stroke-width="2" filter="url(#glow)" opacity="0.8"/>')
    body.append(f'<ellipse cx="{hx}" cy="{hz + 40}" rx="40" ry="6" fill="{CYAN}" opacity="0.35" filter="url(#bigglow)"/>')
    body.append(f'<circle cx="{hx}" cy="{hy}" r="150" fill="url(#core)" opacity="0.35"/>')

    sv, se = icosphere(1)
    iv, ie = icosphere(0)
    holo = [
        f'<g class="float">',
        f'<g filter="url(#glow)">{wireframe(sv, se, hx, hy, 118, 30, 22, CYAN, -0.38)}</g>',
        f'<g filter="url(#glow)">{wireframe(iv, ie, hx, hy, 52, 24, 9, MAGENTA, 0.5, direction=-1, width=1.4, dots=False)}</g>',
        f'<circle cx="{hx}" cy="{hy}" r="9" fill="#fff" filter="url(#glow)"><animate attributeName="r" values="7;11;7" dur="1.8s" repeatCount="indefinite"/></circle>',
    ]
    # tilted orbit ring with a travelling particle (two halves so the back half passes behind the sphere)
    rx, ry = 205, 46
    holo.append(f'<g transform="rotate(-14 {hx} {hy})">'
                f'<path d="M{hx - rx} {hy}A{rx} {ry} 0 0 1 {hx + rx} {hy}" fill="none" stroke="{CYAN}" stroke-opacity="0.25" stroke-dasharray="2 6"/>'
                f'<path d="M{hx - rx} {hy}A{rx} {ry} 0 0 0 {hx + rx} {hy}" fill="none" stroke="{CYAN}" stroke-opacity="0.6" stroke-width="1.4"/>'
                f'<circle r="4.5" fill="#fff" filter="url(#glow)"><animateMotion dur="7s" repeatCount="indefinite" path="M{hx - rx} {hy}A{rx} {ry} 0 0 0 {hx + rx} {hy}A{rx} {ry} 0 0 0 {hx - rx} {hy}"/></circle>'
                f'</g>')
    # floating data tags around the hologram
    tags = [("NEXT.JS", -232, -118, CYAN), ("TYPESCRIPT", 168, -136, MAGENTA), ("IA · LLM", 196, 70, LIME), ("STRIPE", -246, 64, "#8d84ff")]
    for i, (label, dx, dy, col) in enumerate(tags):
        w = len(label) * 8.6 + 22
        x0, y0 = hx + dx, hy + dy
        holo.append(
            f'<g opacity="0.95"><animateTransform attributeName="transform" type="translate" values="0 0;0 {-6 if i % 2 else 6};0 0" dur="{4 + i}s" repeatCount="indefinite"/>'
            f'<line x1="{f(x0 + w / 2)}" y1="{f(y0 + 12)}" x2="{f(hx + dx * 0.35)}" y2="{f(hy + dy * 0.35)}" stroke="{col}" stroke-opacity="0.35" stroke-dasharray="3 3"/>'
            f'<rect x="{f(x0)}" y="{f(y0)}" width="{f(w)}" height="24" rx="4" fill="{BG}" fill-opacity="0.75" stroke="{col}" stroke-opacity="0.8"/>'
            f'<circle cx="{f(x0 + 10)}" cy="{f(y0 + 12)}" r="2.5" fill="{col}" class="pulse"/>'
            f'<text x="{f(x0 + 18)}" y="{f(y0 + 16.5)}" class="mono" font-size="12" font-weight="700" fill="{col}" letter-spacing="1">{label}</text></g>'
        )
    holo.append("</g>")
    body.append("".join(holo))

    # --- left column: identity
    left = 64
    body.append(f'<g>{intro(0.1)}<text x="{left}" y="96" class="mono" font-size="14" fill="{CYAN}" letter-spacing="3">// SYSTEM.ONLINE<tspan fill="#5a6b8a"> — v{now:%Y.%m.%d}</tspan></text></g>')

    name_attrs = f'x="{left}" y="196" class="sans" font-size="78" font-weight="900" letter-spacing="2" textLength="560" lengthAdjust="spacingAndGlyphs"'
    body.append(
        f'<g>{intro(0.35)}'
        f'<g class="rgbL" opacity="0.75"><text {name_attrs} fill="{MAGENTA}">ALISTAIR PIOT</text></g>'
        f'<g class="rgbR" opacity="0.75"><text {name_attrs} fill="{CYAN}">ALISTAIR PIOT</text></g>'
        f'<text {name_attrs} fill="url(#holo)">ALISTAIR PIOT</text>'
        f'<g class="glitch"><g clip-path="url(#sliceA)"><g class="jA"><text {name_attrs} fill="{CYAN}">ALISTAIR PIOT</text></g></g>'
        f'<g clip-path="url(#sliceB)"><g class="jB"><text {name_attrs} fill="{MAGENTA}">ALISTAIR PIOT</text></g></g></g>'
        f'</g>'
    )
    body.append(f'<g>{intro(0.6)}<text x="{left}" y="238" class="sans" font-size="23" font-weight="600" fill="#e8ecff" letter-spacing="0.5">Développeur Freelance Full-Stack</text>'
                f'<rect x="{left}" y="252" width="56" height="3" fill="{MAGENTA}"/><rect x="{left + 60}" y="252" width="18" height="3" fill="{CYAN}"/></g>')

    # cycling typed lines
    phrases = ["> Je transforme des idées en produits web.", "> SaaS · apps métier · logiciels web.", "> Rapides à lancer, pensés pour scaler.", "> Next.js · TypeScript · IA"]
    period = 3.6
    total = period * len(phrases)
    typed = [f'<defs>']
    for i, p in enumerate(phrases):
        w = len(p) * 10.3 + 4
        k0, k1, k2, k3 = (i * period) / total, (i * period + 1.4) / total, (i * period + period - 0.35) / total, ((i + 1) * period) / total
        kt = sorted({0, k0, k1, k2, k3, 1})
        vals = {0: 0, k0: 0, k1: w, k2: w, k3: 0, 1: 0}
        typed.append(f'<clipPath id="type{i}"><rect x="{left}" y="270" height="34" width="0">'
                     f'<animate attributeName="width" values="{";".join(f(vals[k]) for k in kt)}" keyTimes="{";".join(f"{k:.4f}" for k in kt)}" dur="{total}s" repeatCount="indefinite"/></rect></clipPath>')
    typed.append("</defs>")
    for i, p in enumerate(phrases):
        typed.append(f'<text x="{left}" y="292" class="mono" font-size="17" fill="#b9c4e6" clip-path="url(#type{i})" xml:space="preserve">{html.escape(p)}</text>')
    body.append(f'<g>{intro(0.85)}{"".join(typed)}</g>')

    # status pill + HUD readouts
    since = dt.date(2022, 2, 14)
    body.append(
        f'<g transform="translate({left} 330)"><g>{intro(0.85)}'
        f'<rect width="268" height="34" rx="17" fill="{LIME}" fill-opacity="0.08" stroke="{LIME}" stroke-opacity="0.6"/>'
        f'<circle cx="20" cy="17" r="5" fill="{LIME}"/><circle cx="20" cy="17" r="5" fill="none" stroke="{LIME}" class="ring"/>'
        f'<text x="36" y="22" class="mono" font-size="13" font-weight="700" fill="{LIME}" letter-spacing="1.5">DISPONIBLE · MISSIONS</text></g></g>'
    )
    readouts = [
        ("REPOS PUBLICS", f"{stats['repos']}"),
        ("PROJETS SAAS", f"{len(PROJECTS)}"),
        ("ON GITHUB", f"{(now.date() - since).days} j"),
        ("LAST SYNC", f"{now:%d.%m.%Y}"),
    ]
    rx0 = left
    body.append(f'<rect x="{left - 18}" y="390" width="566" height="76" rx="10" fill="{BG}" fill-opacity="0.82" stroke="#1d2440"/>')
    for i, (k, v) in enumerate(readouts):
        x = rx0 + i * 132
        body.append(f'<g>{intro(0.85)}<text x="{x}" y="412" class="mono" font-size="10.5" fill="#5f6f93" letter-spacing="1.5">{k}</text>'
                    f'<text x="{x}" y="438" class="mono" font-size="19" font-weight="700" fill="#fff">{v}</text>'
                    f'<rect x="{x}" y="448" width="{110 if i < 3 else 120}" height="2" fill="#1d2440"/>'
                    f'<rect x="{x}" y="448" width="0" height="2" fill="{[CYAN, MAGENTA, LIME, AMBER][i]}"><animate attributeName="width" values="0;{[96, 64, 84, 120][i]}" dur="1.6s" begin="{0.9 + i * 0.2:.1f}s" fill="freeze"/></rect></g>')

    body.append(hud_corners(14, 14, W - 28, H - 28, 22, CYAN, 0.5))
    body.append(f'<text x="{W - 40}" y="40" text-anchor="end" class="mono" font-size="11" fill="#5f6f93" letter-spacing="2">FR · REMOTE · UTC+1</text>')
    body.append(f'<text x="{W - 40}" y="{H - 30}" text-anchor="end" class="mono" font-size="11" fill="#5f6f93" letter-spacing="2">RENDER: PURE SVG · NO JS · AUTO-SYNC DAILY</text>')
    body.append(scan_beam("beamV", W, H, 7))
    body.append(scanlines("scan", W, H))
    write("hero.svg", svg(W, H, "".join(body), "Alistair Piot — Développeur Freelance Full-Stack"))


# --------------------------------------------------------------------------- section headers

def build_header(slug, index, label, sub):
    W, H = 1200, 84
    body = f"""<style>
@keyframes draw{{from{{stroke-dashoffset:900}}to{{stroke-dashoffset:0}}}}
.line{{stroke-dasharray:900;animation:draw 2.4s cubic-bezier(.2,.8,.2,1) .2s both}}
@keyframes run{{from{{transform:translateX(0)}}to{{transform:translateX(840px)}}}}
.run{{animation:run 3.5s linear infinite}}
@keyframes blink{{0%,49%{{opacity:1}}50%,100%{{opacity:0}}}}
.cursor{{animation:blink 1s steps(1) infinite}}
</style>
<defs><linearGradient id="hl{slug}" x1="0" x2="1"><stop offset="0" stop-color="{CYAN}"/><stop offset="0.5" stop-color="{MAGENTA}"/><stop offset="1" stop-color="{MAGENTA}" stop-opacity="0"/></linearGradient></defs>
<text x="0" y="50" font-family="{MONO}" font-size="15" fill="{CYAN}" letter-spacing="2">{index}</text>
<text x="48" y="52" font-family="{SANS}" font-size="30" font-weight="800" fill="#ffffff" letter-spacing="1">{html.escape(label)}</text>
<rect x="{58 + len(label) * 19}" y="30" width="12" height="24" fill="{MAGENTA}" class="cursor"/>
<text x="1200" y="50" text-anchor="end" font-family="{MONO}" font-size="12" fill="#6b7aa0" letter-spacing="2">{html.escape(sub)}</text>
<path d="M0 70H1200" stroke="#1b2140" stroke-width="2"/>
<path d="M0 70H900" stroke="url(#hl{slug})" stroke-width="2" class="line"/>
<g class="run"><rect x="0" y="68" width="60" height="4" rx="2" fill="#fff" opacity="0.9"/></g>"""
    write(f"header-{slug}.svg", svg(W, H, body, label))


# --------------------------------------------------------------------------- project cards

def glyph(kind, cx, cy, accent):
    if kind == "pay":  # payment link: a coin spinning in 3D (scaleX oscillation) inside a pulse ring
        return (f'<g transform="translate({cx} {cy})">'
                f'<circle r="34" fill="none" stroke="{accent}" stroke-opacity="0.25"/><circle r="34" fill="none" stroke="{accent}" stroke-width="2" stroke-dasharray="40 174">'
                f'<animateTransform attributeName="transform" type="rotate" values="0;360" dur="3s" repeatCount="indefinite"/></circle>'
                f'<g><animateTransform attributeName="transform" type="scale" values="1 1;0.08 1;1 1;0.08 1;1 1" dur="3.2s" repeatCount="indefinite" calcMode="spline" keySplines=".45 0 .55 1;.45 0 .55 1;.45 0 .55 1;.45 0 .55 1"/>'
                f'<circle r="22" fill="{accent}" fill-opacity="0.15" stroke="{accent}" stroke-width="2.5"/>'
                f'<text y="9" text-anchor="middle" font-family="{SANS}" font-size="26" font-weight="900" fill="{accent}">€</text></g></g>')
    if kind == "twin":  # digital twin: two orbiting nodes linked by a synapse
        return (f'<g transform="translate({cx} {cy})">'
                f'<circle r="34" fill="none" stroke="{accent}" stroke-opacity="0.25" stroke-dasharray="3 4"/>'
                f'<g><animateTransform attributeName="transform" type="rotate" values="0;360" dur="5s" repeatCount="indefinite"/>'
                f'<line x1="-22" y1="0" x2="22" y2="0" stroke="{accent}" stroke-width="1.5" stroke-dasharray="4 3"><animate attributeName="stroke-dashoffset" values="0;-14" dur="0.6s" repeatCount="indefinite"/></line>'
                f'<circle cx="-22" r="9" fill="{accent}" fill-opacity="0.2" stroke="{accent}" stroke-width="2"/>'
                f'<circle cx="22" r="9" fill="#fff" fill-opacity="0.15" stroke="#fff" stroke-width="2"/></g>'
                f'<circle r="4" fill="#fff"><animate attributeName="r" values="3;6;3" dur="1.5s" repeatCount="indefinite"/></circle></g>')
    # vasy: an isometric cube (craft object) being assembled
    s = 20
    top = f"0,{-s} {s * 0.87:.1f},{-s / 2} 0,0 {-s * 0.87:.1f},{-s / 2}"
    lft = f"{-s * 0.87:.1f},{-s / 2} 0,0 0,{s} {-s * 0.87:.1f},{s / 2}"
    rgt = f"{s * 0.87:.1f},{-s / 2} 0,0 0,{s} {s * 0.87:.1f},{s / 2}"
    return (f'<g transform="translate({cx} {cy})">'
            f'<circle r="34" fill="none" stroke="{accent}" stroke-opacity="0.25"/>'
            f'<polygon points="{top}" fill="{accent}" fill-opacity="0.45" stroke="{accent}"><animateTransform attributeName="transform" type="translate" values="0 -14;0 0;0 0;0 -14" keyTimes="0;0.3;0.8;1" dur="3s" repeatCount="indefinite"/></polygon>'
            f'<polygon points="{lft}" fill="{accent}" fill-opacity="0.15" stroke="{accent}"><animateTransform attributeName="transform" type="translate" values="-12 7;0 0;0 0;-12 7" keyTimes="0;0.3;0.8;1" dur="3s" repeatCount="indefinite"/></polygon>'
            f'<polygon points="{rgt}" fill="{accent}" fill-opacity="0.28" stroke="{accent}"><animateTransform attributeName="transform" type="translate" values="12 7;0 0;0 0;12 7" keyTimes="0;0.3;0.8;1" dur="3s" repeatCount="indefinite"/></polygon></g>')


def build_card(p, i, n):
    W, H = 390, 300
    a = p["accent"]
    sid = p["slug"]
    live = p["status"] == "LIVE"
    st_col = LIME if live else AMBER
    body = [f"""<defs>
<linearGradient id="bd{sid}" x1="0" y1="0" x2="{W}" y2="{H}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{a}"/><stop offset="0.35" stop-color="{a}" stop-opacity="0.05"/><stop offset="0.65" stop-color="{VIOLET}" stop-opacity="0.05"/><stop offset="1" stop-color="{VIOLET}"/>
<animateTransform attributeName="gradientTransform" type="rotate" values="0 {W / 2} {H / 2};360 {W / 2} {H / 2}" dur="6s" repeatCount="indefinite"/></linearGradient>
<radialGradient id="gl{sid}" cx="0.85" cy="0.1" r="0.8"><stop offset="0" stop-color="{a}" stop-opacity="0.22"/><stop offset="1" stop-color="{a}" stop-opacity="0"/></radialGradient>
<linearGradient id="sh{sid}" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.5" stop-color="#fff" stop-opacity="0.09"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<clipPath id="cp{sid}"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="16"/></clipPath>
<pattern id="dots{sid}" width="16" height="16" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#fff" opacity="0.06"/></pattern>
</defs>
<style>@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}.pulse{{animation:pulse 1.4s ease-in-out infinite}}
@keyframes up{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:none}}}}.up{{animation:up .8s {0.15 + i * 0.2:.2f}s both}}</style>""",
            f'<g class="up">',
            f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="16" fill="#070914"/>',
            f'<g clip-path="url(#cp{sid})"><rect width="{W}" height="{H}" fill="url(#dots{sid})"/><rect width="{W}" height="{H}" fill="url(#gl{sid})"/>'
            f'<rect x="-200" y="0" width="160" height="{H}" fill="url(#sh{sid})" transform="skewX(-20)"><animate attributeName="x" values="-260;{W + 120}" dur="4.5s" begin="{i * 1.2:.1f}s" repeatCount="indefinite"/></rect></g>',
            f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="16" fill="none" stroke="url(#bd{sid})" stroke-width="2"/>',
            f'<text x="26" y="40" font-family="{MONO}" font-size="12" fill="#5f6f93" letter-spacing="2">PROJECT_{i + 1:02d}/{n:02d}</text>',
            f'<g transform="translate({W - 26} 26)"><rect x="-{82 if live else 92}" y="0" width="{82 if live else 92}" height="24" rx="12" fill="{st_col}" fill-opacity="0.1" stroke="{st_col}" stroke-opacity="0.6"/>'
            f'<circle cx="-{68 if live else 78}" cy="12" r="4" fill="{st_col}" class="pulse"/>'
            f'<text x="-{56 if live else 66}" y="16.5" font-family="{MONO}" font-size="11.5" font-weight="700" fill="{st_col}" letter-spacing="1.5">{p["status"]}</text></g>',
            glyph(p["glyph"], 62, 108, a),
            f'<text x="112" y="104" font-family="{SANS}" font-size="30" font-weight="800" fill="#fff">{p["name"]}</text>',
            f'<text x="113" y="128" font-family="{MONO}" font-size="12" fill="{a}" letter-spacing="1">{html.escape(p["url"].replace("https://", "") if p["url"] else "bientôt en ligne")}</text>',
            ]
    for j, line in enumerate(p["lines"]):
        body.append(f'<text x="26" y="{178 + j * 22}" font-family="{SANS}" font-size="14.5" fill="#aab4d4">{html.escape(line)}</text>')
    x = 26
    for label, col in p["tags"]:
        w = len(label) * 8 + 20
        body.append(f'<rect x="{x}" y="252" width="{w}" height="24" rx="6" fill="{col}" fill-opacity="0.1" stroke="{col}" stroke-opacity="0.45"/>'
                    f'<text x="{x + w / 2}" y="268.5" text-anchor="middle" font-family="{MONO}" font-size="12" font-weight="700" fill="{col}">{label}</text>')
        x += w + 8
    if p["url"]:
        body.append(f'<text x="{W - 26}" y="269" text-anchor="end" font-family="{MONO}" font-size="13" font-weight="700" fill="{a}">VISITER →<animate attributeName="opacity" values="1;0.5;1" dur="2s" repeatCount="indefinite"/></text>')
    else:
        # build progress bar
        body.append(f'<rect x="{W - 136}" y="261" width="110" height="5" rx="2.5" fill="#1b2140"/>'
                    f'<rect x="{W - 136}" y="261" width="0" height="5" rx="2.5" fill="{a}"><animate attributeName="width" values="0;84;78;96;0" keyTimes="0;0.4;0.55;0.9;1" dur="6s" repeatCount="indefinite"/></rect>'
                    f'<text x="{W - 26}" y="252" text-anchor="end" font-family="{MONO}" font-size="10" fill="#5f6f93" letter-spacing="1.5">BUILDING</text>')
    body.append("</g>")
    write(f"card-{sid}.svg", svg(W, H, "".join(body), f"{p['name']} — {' '.join(p['lines'])}"))


# --------------------------------------------------------------------------- stack orbits

def build_stack():
    W, H = 1200, 470
    cx, cy = 600, 235
    frames = 48
    body = [f"""<defs>
<radialGradient id="sbg" cx="0.5" cy="0.5" r="0.6"><stop offset="0" stop-color="#1a0b3d"/><stop offset="1" stop-color="{BG}"/></radialGradient>
<radialGradient id="nucleus" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#fff"/><stop offset="0.3" stop-color="{CYAN}" stop-opacity="0.8"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>
<filter id="sglow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>""",
            f'<rect width="{W}" height="{H}" rx="18" fill="url(#sbg)"/>',
            stars(random.Random(3), 60, W, H)]

    rings = [(1.0, 0.18, 0.0, 34), (1.55, -0.32, 0.9, 46), (2.1, 0.22, 2.0, 60)]
    scale = 98
    back, front = [], []
    for (radius, tilt_z, phase, dur), (label, col, items) in zip(rings, STACK_RINGS):
        # ring outline
        pts = []
        for s in range(97):
            a = 2 * math.pi * s / 96
            p = rot((radius * math.cos(a), 0, radius * math.sin(a)), 1.22, 0, tilt_z)
            x, y, _ = project(p, cx, cy, scale, cam=7)
            pts.append(f"{f(x)} {f(y)}")
        back.append(f'<path d="M{"L".join(pts)}Z" fill="none" stroke="{col}" stroke-opacity="0.35" stroke-width="1.2"/>')
        # orbiting items: position, scale and opacity baked per frame
        for k, item in enumerate(items):
            xs, ys, ss, ops = [], [], [], []
            for fr in range(frames + 1):
                a = phase + 2 * math.pi * (k / len(items) + fr / frames)
                p = rot((radius * math.cos(a), 0, radius * math.sin(a)), 1.22, 0, tilt_z)
                x, y, z = project(p, cx, cy, scale, cam=7)
                depth = (z / radius + 1) / 2
                xs.append(f"{f(x)} {f(y)}")
                ss.append(f"{0.62 + 0.5 * depth:.2f}")
                ops.append(f"{0.3 + 0.7 * depth:.2f}")
            w = len(item) * 8.4 + 34
            common = f'dur="{dur}s" repeatCount="indefinite"'
            front.append(
                f'<g><animateTransform attributeName="transform" type="translate" values="{";".join(xs)}" {common}/>'
                f'<animateTransform attributeName="transform" type="scale" values="{";".join(ss)}" {common} additive="sum"/>'
                f'<animate attributeName="opacity" values="{";".join(ops)}" {common}/>'
                f'<rect x="{f(-w / 2)}" y="-15" width="{f(w)}" height="30" rx="15" fill="#080a18" stroke="{col}" stroke-width="1.5"/>'
                f'<circle cx="{f(-w / 2 + 15)}" cy="0" r="4" fill="{col}"/>'
                f'<text x="{f(-w / 2 + 26)}" y="5" font-family="{MONO}" font-size="13.5" font-weight="700" fill="#fff">{html.escape(item)}</text></g>'
            )
    body.append("".join(back))
    body.append(f'<circle cx="{cx}" cy="{cy}" r="90" fill="url(#nucleus)" opacity="0.55"><animate attributeName="r" values="80;96;80" dur="3s" repeatCount="indefinite"/></circle>')
    iv, ie = icosphere(0)
    body.append(f'<g filter="url(#sglow)">{wireframe(iv, ie, cx, cy, 40, 24, 10, "#ffffff", 0.4, width=1.3, dots=False)}</g>')
    body.append(f'<text x="{cx}" y="{cy + 5}" text-anchor="middle" font-family="{MONO}" font-size="14" font-weight="800" fill="{BG}" letter-spacing="1">AP</text>')
    body.append(f'<g filter="url(#sglow)">{"".join(front)}</g>')

    # legend
    for i, (label, col, items) in enumerate(STACK_RINGS):
        y = 52 + i * 26
        body.append(f'<rect x="40" y="{y - 10}" width="14" height="3" fill="{col}"/><text x="62" y="{y - 3}" font-family="{MONO}" font-size="12" fill="#c9d2f0" letter-spacing="2">ORBIT_{i + 1:02d} · {label}</text>')
    body.append(f'<text x="{W - 40}" y="{H - 30}" text-anchor="end" font-family="{MONO}" font-size="11" fill="#5f6f93" letter-spacing="2">3D ORBITAL MAP · {sum(len(r[2]) for r in STACK_RINGS)} TECHNOLOGIES</text>')
    body.append(hud_corners(14, 14, W - 28, H - 28, 18, MAGENTA, 0.45))
    write("stack.svg", svg(W, H, "".join(body), "Stack : Next.js, React, TypeScript, Tailwind, shadcn/ui, Node.js, Prisma, PostgreSQL, Supabase, REST, Vercel, Stripe, Figma, Git, Notion"))


# --------------------------------------------------------------------------- contribution city

def build_city(weeks, stats, repos, now):
    W, H = 1200, 600
    a = 14          # iso cell size
    kx, ky = 0.866, 0.5
    ox, oy = 450, 150
    maxc = max([c for w in weeks for _, c, _ in w] + [1])
    colors = ["#151a33", "#3b1f8f", "#7c3aed", "#d946ef", "#00f0ff"]

    body = [f"""<defs>
<radialGradient id="cbg" cx="0.6" cy="0.6" r="0.7"><stop offset="0" stop-color="#170a35"/><stop offset="1" stop-color="{BG}"/></radialGradient>
<filter id="cglow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>
<style>@keyframes rise{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}
.b{{transform-box:fill-box;transform-origin:50% 100%;animation:rise 1.1s cubic-bezier(.2,.9,.25,1.15) both}}
@keyframes wave{{0%,100%{{opacity:0}}6%{{opacity:.95}}14%{{opacity:0}}}}
.w{{animation:wave 9s linear infinite}}</style>""",
            f'<rect width="{W}" height="{H}" rx="18" fill="url(#cbg)"/>', stars(random.Random(11), 40, W, H)]

    def iso(wk, d):
        return ox + (wk - d) * a * kx, oy + (wk + d) * a * ky

    # ground plate
    nw = len(weeks)
    c0, c1, c2, c3 = iso(-0.6, -0.6), iso(nw - 0.4, -0.6), iso(nw - 0.4, 6.6), iso(-0.6, 6.6)
    body.append(f'<polygon points="{f(c0[0])},{f(c0[1])} {f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} {f(c3[0])},{f(c3[1])}" fill="#0b0f24" stroke="{CYAN}" stroke-opacity="0.35"/>')
    body.append(f'<polygon points="{f(c3[0])},{f(c3[1])} {f(c2[0])},{f(c2[1])} {f(c2[0])},{f(c2[1] + 10)} {f(c3[0])},{f(c3[1] + 10)}" fill="#0a0d1d" stroke="{CYAN}" stroke-opacity="0.2"/>')
    body.append(f'<polygon points="{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} {f(c2[0])},{f(c2[1] + 10)} {f(c1[0])},{f(c1[1] + 10)}" fill="#070917" stroke="{CYAN}" stroke-opacity="0.2"/>')

    cells = [(wk, d, *weeks[wk][d]) for wk in range(nw) for d in range(len(weeks[wk]))]
    cells.sort(key=lambda c: (c[0] + c[1], c[0]))  # painter's order: back to front
    hw, hh = a * kx * 0.42, a * ky * 0.42
    bars = []
    for wk, d, date, count, level in cells:
        x, y = iso(wk, d)
        h = 2 + (math.sqrt(count / maxc) * 120 if count else 0)
        col = colors[level]
        top = f"{f(x)},{f(y - hh - h)} {f(x + hw)},{f(y - h)} {f(x)},{f(y + hh - h)} {f(x - hw)},{f(y - h)}"
        left = f"{f(x - hw)},{f(y - h)} {f(x)},{f(y + hh - h)} {f(x)},{f(y + hh)} {f(x - hw)},{f(y)}"
        right = f"{f(x + hw)},{f(y - h)} {f(x)},{f(y + hh - h)} {f(x)},{f(y + hh)} {f(x + hw)},{f(y)}"
        delay = (wk + d) * 0.022
        g = (f'<g class="b" style="animation-delay:{delay:.2f}s"><title>{date} : {count} contribution{"s" if count != 1 else ""}</title>'
             f'<polygon points="{left}" fill="{col}" fill-opacity="0.75"/><polygon points="{right}" fill="{col}" fill-opacity="0.5"/>'
             f'<polygon points="{top}" fill="{col}"/>')
        if count:
            g += f'<polygon points="{top}" fill="#fff" class="w" style="animation-delay:{(wk - d) * 0.1 + 1.5:.2f}s" opacity="0"/>'
        bars.append(g + "</g>")
    body.append(f'<g filter="url(#cglow)">{"".join(bars)}</g>')

    # month labels along the front-left edge
    seen = set()
    for wk, week in enumerate(weeks):
        day = dt.date.fromisoformat(week[0][0])
        if day.day <= 7 and (day.year, day.month) not in seen and wk < nw - 1:
            seen.add((day.year, day.month))
            x, y = iso(wk, 7.6)
            label = ["JAN", "FÉV", "MAR", "AVR", "MAI", "JUN", "JUL", "AOÛ", "SEP", "OCT", "NOV", "DÉC"][day.month - 1]
            body.append(f'<text x="{f(x)}" y="{f(y)}" font-family="{MONO}" font-size="10" fill="#5f6f93" transform="rotate(30 {f(x)} {f(y)})">{label}</text>')

    # stats panel (top-left void of the isometric layout)
    best_date, best_count, _ = stats["best"]
    langs = {}
    for r in repos:
        if r.get("language"):
            langs[r["language"]] = langs.get(r["language"], 0) + 1
    top_langs = sorted(langs.items(), key=lambda kv: -kv[1])[:5]
    lang_cols = {"TypeScript": "#3178c6", "JavaScript": "#f1e05a", "PHP": "#8892bf", "Rust": "#dea584", "HTML": "#e34c26", "Svelte": "#ff3e00", "CSS": "#663399", "SCSS": "#c6538c", "Lua": "#000080", "Python": "#3572A5"}
    rows = [
        ("CONTRIBUTIONS · 12 MOIS", f"{stats['total']:,}".replace(",", " "), CYAN),
        ("RECORD DE STREAK", f"{stats['longest']} jours", MAGENTA),
        ("JOURS ACTIFS", f"{stats['active']}", LIME),
        ("PIC D'ACTIVITÉ", f"{best_count} · {dt.date.fromisoformat(best_date):%d.%m.%y}" if best_date else "—", AMBER),
    ]
    px, py = 44, 50
    body.append(f'<text x="{px}" y="{py}" font-family="{MONO}" font-size="13" fill="{CYAN}" letter-spacing="3">// COMMIT_CITY.render()</text>')
    for i, (k, v, col) in enumerate(rows):
        y = py + 40 + i * 54
        body.append(f'<rect x="{px}" y="{y - 14}" width="3" height="40" fill="{col}"/>'
                    f'<text x="{px + 14}" y="{y}" font-family="{MONO}" font-size="10.5" fill="#6b7aa0" letter-spacing="1.5">{k}</text>'
                    f'<text x="{px + 14}" y="{y + 24}" font-family="{SANS}" font-size="22" font-weight="800" fill="#fff">{html.escape(v)}</text>')
    if top_langs:
        y = py + 40 + 4 * 54 + 4
        total = sum(c for _, c in top_langs)
        body.append(f'<text x="{px}" y="{y}" font-family="{MONO}" font-size="10.5" fill="#6b7aa0" letter-spacing="1.5">LANGAGES · {len(repos)} REPOS PUBLICS</text>')
        x = px
        for lang, c in top_langs:
            w = 230 * c / total
            body.append(f'<rect x="{f(x)}" y="{y + 10}" width="{f(max(w - 2, 1))}" height="8" rx="2" fill="{lang_cols.get(lang, "#888")}"/>')
            x += w
        for i, (lang, c) in enumerate(top_langs):
            lx, ly = px + (i % 3) * 82, y + 38 + (i // 3) * 18
            body.append(f'<circle cx="{lx + 4}" cy="{ly - 4}" r="4" fill="{lang_cols.get(lang, "#888")}"/><text x="{lx + 12}" y="{ly}" font-family="{MONO}" font-size="11" fill="#aab4d4">{lang}</text>')

    # legend (bottom-right void)
    lx, ly = W - 300, H - 78
    body.append(f'<text x="{lx}" y="{ly - 14}" font-family="{MONO}" font-size="10.5" fill="#6b7aa0" letter-spacing="1.5">INTENSITÉ</text>')
    for i, c in enumerate(colors):
        body.append(f'<rect x="{lx + i * 22}" y="{ly - 4}" width="16" height="16" rx="3" fill="{c}"/>')
    body.append(f'<text x="{lx}" y="{ly + 36}" font-family="{MONO}" font-size="10.5" fill="#6b7aa0" letter-spacing="1">LIVE · SYNC {now:%d.%m.%Y %H:%M} UTC</text>')
    body.append(hud_corners(14, 14, W - 28, H - 28, 18, CYAN, 0.45))
    write("commit-city.svg", svg(W, H, "".join(body), f"Contributions GitHub en 3D : {stats['total']} sur les 12 derniers mois"))


# --------------------------------------------------------------------------- footer & buttons

def build_footer():
    W, H = 1200, 220
    # EKG-like transmission line
    pts, x = [], 0
    rnd = random.Random(5)
    while x <= W:
        if 260 < x < 940 and rnd.random() < 0.12:
            pts += [(x, 70), (x + 8, 70 - rnd.uniform(18, 46)), (x + 16, 70 + rnd.uniform(10, 28)), (x + 24, 70)]
            x += 34
        else:
            pts.append((x, 70 + rnd.uniform(-1.5, 1.5)))
            x += 12
    d = "M" + "L".join(f"{f(px)} {f(py)}" for px, py in pts)
    body = f"""<defs><linearGradient id="fl" x1="0" x2="1"><stop offset="0" stop-color="{CYAN}" stop-opacity="0"/><stop offset="0.3" stop-color="{CYAN}"/><stop offset="0.7" stop-color="{MAGENTA}"/><stop offset="1" stop-color="{MAGENTA}" stop-opacity="0"/></linearGradient>
<filter id="fg" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
<style>@keyframes sig{{from{{stroke-dashoffset:2600}}to{{stroke-dashoffset:0}}}}.sig{{stroke-dasharray:1300;animation:sig 4s linear infinite}}
@keyframes blink{{0%,49%{{opacity:1}}50%,100%{{opacity:0}}}}.cursor{{animation:blink 1s steps(1) infinite}}</style>
<path d="{d}" fill="none" stroke="#1b2140" stroke-width="2"/>
<path d="{d}" fill="none" stroke="url(#fl)" stroke-width="2.2" class="sig" filter="url(#fg)"/>
<text x="600" y="140" text-anchor="middle" font-family="{SANS}" font-size="30" font-weight="800" fill="#fff">Un projet en tête ? Parlons-en.</text>
<text x="600" y="176" text-anchor="middle" font-family="{MONO}" font-size="14" fill="#8a97bd" letter-spacing="2">INCOMING_TRANSMISSION — réponse sous 24h<tspan fill="{CYAN}" class="cursor"> ▌</tspan></text>"""
    write("footer.svg", svg(W, H, body, "Un projet en tête ? Parlons-en."))


def build_button(slug, label, icon, col):
    W, H = 250, 56
    icons = {
        "globe": f'<circle r="9" fill="none" stroke="{col}" stroke-width="2"/><ellipse rx="4" ry="9" fill="none" stroke="{col}" stroke-width="1.6"/><path d="M-9 0H9" stroke="{col}" stroke-width="1.6"/>',
        "in": f'<rect x="-10" y="-10" width="20" height="20" rx="4" fill="{col}"/><text y="5.5" text-anchor="middle" font-family="{SANS}" font-size="13" font-weight="900" fill="{BG}">in</text>',
    }
    body = f"""<defs><linearGradient id="b{slug}" x1="0" y1="0" x2="{W}" y2="0" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{col}"/><stop offset="0.5" stop-color="{col}" stop-opacity="0.1"/><stop offset="1" stop-color="{col}"/>
<animateTransform attributeName="gradientTransform" type="translate" values="-{W} 0;{W} 0" dur="3s" repeatCount="indefinite"/></linearGradient></defs>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="10" fill="#070914"/>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="10" fill="{col}" fill-opacity="0.07" stroke="url(#b{slug})" stroke-width="2"/>
<g transform="translate(34 28)">{icons[icon]}</g>
<text x="58" y="33.5" font-family="{MONO}" font-size="15" font-weight="800" fill="#fff" letter-spacing="2">{label}</text>
<text x="{W - 22}" y="34" text-anchor="end" font-family="{MONO}" font-size="16" font-weight="800" fill="{col}">→<animate attributeName="x" values="{W - 24};{W - 18};{W - 24}" dur="1.4s" repeatCount="indefinite"/></text>"""
    write(f"btn-{slug}.svg", svg(W, H, body, label))


# --------------------------------------------------------------------------- main

def main():
    now = dt.datetime.now(dt.timezone.utc)
    print("fetching data…")
    weeks = fetch_contributions()
    repos = fetch_repos()
    stats = contribution_stats(weeks)
    stats["repos"] = len(repos)
    print(f"  {stats['total']} contributions, {len(repos)} repos")
    print("rendering…")
    build_hero(stats, now)
    build_header("projects", "01", "PROJETS", "SHIPPED & IN PROGRESS")
    build_header("stack", "02", "STACK", "ORBITAL TECH MAP")
    build_header("city", "03", "ACTIVITÉ", "LIVE · REGENERATED DAILY")
    for i, p in enumerate(PROJECTS):
        build_card(p, i, len(PROJECTS))
    build_stack()
    build_city(weeks, stats, repos, now)
    build_footer()
    build_button("portfolio", "PORTFOLIO", "globe", CYAN)
    build_button("linkedin", "LINKEDIN", "in", "#2f8fff")


if __name__ == "__main__":
    main()
