#!/usr/bin/env python3
"""Rebuild the self-updating parts of my GitHub profile README.

Usage:
  python3 scripts/build_profile.py              # live data
  python3 scripts/build_profile.py --fixtures F # data from a JSON file (for testing)

Updates, in place:
- README.md sections between <!-- NAME:START --> and <!-- NAME:END -->:
  BLOG-POSTS, GISTS, REPOS
- assets/map-dark.svg, assets/map-light.svg: a mind map of projects and posts
- assets/listening-dark.svg, assets/listening-light.svg: last track from Last.fm

Environment (all optional; a section is left alone if its data can't be fetched):
  GITHUB_TOKEN     raises the GitHub API rate limit
  LASTFM_API_KEY   turns on the Last.fm card
  LASTFM_USER      Last.fm username

Standard library only.
"""
import argparse
import html
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
ASSETS = ROOT / "assets"

GITHUB_USER = "benkelly"
BLOG_RSS = "https://blog.benjamin.ie/api/rss"
SKIP_REPOS = {"benkelly"}  # this repo

# Projects on the map, and which blog post belongs to each (by slug).
PROJECTS = [
    {"name": "mentat", "post": "mentat"},
    {"name": "cv-pipeline", "post": "my-cv-is-a-ci-pipeline"},
    {"name": "scrobSter", "post": "scrobster"},
    {"name": "MercurySandbox", "post": "mercurysandbox"},
    {"name": "NiFi + Azure AD", "post": "nifi-azure-ad-authentication"},
]

THEMES = {
    "dark": {"bg": "#0e0f11", "panel": "#16181b", "gold": "#d4a94b", "silver": "#b8bec7",
             "line": "#34373c", "text": "#e8e6e1", "muted": "#8a8f98"},
    "light": {"bg": "#fafaf7", "panel": "#f1f0ec", "gold": "#9a7425", "silver": "#5f6670",
              "line": "#d6d4ce", "text": "#1c1c1c", "muted": "#6b6f76"},
}
FONT = "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"


# ---------- fetching ----------

def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "benkelly-profile-readme", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def github(path, auth=True):
    headers = {"Accept": "application/vnd.github+json"}
    # The Actions token can't read gists (403), so gists go unauthenticated.
    if auth and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    return json.loads(get(f"https://api.github.com{path}", headers))


def blog_posts(n=5):
    posts = []
    for item in ET.fromstring(get(BLOG_RSS)).iter("item"):
        link = (item.findtext("link") or "").strip().rstrip("/")
        title = (item.findtext("title") or "").strip()
        when = item.findtext("pubDate")
        if not link.startswith("https://blog.benjamin.ie/blog/") or not title or not when:
            continue
        if link.endswith("/hello-world"):
            continue
        posts.append({"title": title, "url": link, "slug": link.rsplit("/", 1)[-1],
                      "date": parsedate_to_datetime(when).date().isoformat()})
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts[:n]


def gists(n=4):
    out = []
    for g in github(f"/users/{GITHUB_USER}/gists?per_page=30", auth=False):
        if not g.get("public"):
            continue
        files = list(g.get("files", {}))
        out.append({"title": (g.get("description") or "").strip() or (files[0] if files else g["id"][:8]),
                    "url": g["html_url"], "date": g["created_at"][:10]})
    out.sort(key=lambda g: g["date"], reverse=True)
    return out[:n]


def repos(n=5):
    out = []
    for r in github(f"/users/{GITHUB_USER}/repos?sort=pushed&type=owner&per_page=50"):
        if r.get("private") or r.get("fork") or r.get("archived") or r["name"] in SKIP_REPOS:
            continue
        out.append({"name": r["name"], "url": r["html_url"], "desc": (r.get("description") or "").strip(),
                    "lang": r.get("language") or "", "date": r["pushed_at"][:10]})
    return out[:n]


def lastfm():
    key, user = os.environ.get("LASTFM_API_KEY"), os.environ.get("LASTFM_USER")
    if not key or not user:
        return None
    q = urllib.parse.urlencode({"method": "user.getrecenttracks", "user": user, "api_key": key,
                                "format": "json", "limit": 1})
    tracks = json.loads(get(f"https://ws.audioscrobbler.com/2.0/?{q}"))["recenttracks"]["track"]
    if not tracks:
        return None
    t = tracks[0]
    now = t.get("@attr", {}).get("nowplaying") == "true"
    when = None if now else datetime.fromtimestamp(int(t["date"]["uts"]), timezone.utc)
    return {"track": t["name"], "artist": t["artist"]["#text"], "now": now, "when": when}


# ---------- README sections ----------

def md(s):
    return re.sub(r"([\[\]|])", r"\\\1", s)


def short_date(iso):
    return datetime.fromisoformat(iso).strftime("%d %b %Y")


def replace_section(text, name, body):
    start, end = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    if start not in text or end not in text:
        return text
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    return f"{before}{start}\n{body}\n{end}{after}"


def render_posts(items):
    return "\n".join(f"- [{md(p['title'])}]({p['url']}) · {short_date(p['date'])}" for p in items)


def render_gists(items):
    return "\n".join(f"- [{md(g['title'])}]({g['url']}) · {short_date(g['date'])}" for g in items)


def render_repos(items):
    rows = ["| Repo | What | Pushed |", "| --- | --- | --- |"]
    for r in items:
        what = md(r["desc"]) or "—"
        if r["lang"]:
            what += f" <sub>{html.escape(r['lang'])}</sub>"
        rows.append(f"| [{md(r['name'])}]({r['url']}) | {what} | {short_date(r['date'])} |")
    return "\n".join(rows)


# ---------- SVGs ----------

def esc(s):
    return html.escape(s, quote=True)


def trim(s, n):
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def map_svg(theme, posts):
    c = THEMES[theme]
    W, H, cx, cy = 880, 340, 400, 175
    titles = {p["slug"]: p["title"] for p in posts}
    left = [p["name"] for p in PROJECTS]
    right = [trim(p["title"].split(":")[0], 28) for p in posts]
    post_slugs = [p["slug"] for p in posts]

    def arc(count, start, end):
        if count == 1:
            return [(start + end) / 2]
        return [start + (end - start) * i / (count - 1) for i in range(count)]

    # Projects on a left arc, posts on a right one. Right labels are longer,
    # so that arc is narrower.
    ry = 125
    lpos = [(cx + 250 * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a)))
            for a in arc(len(left), 230, 130)]
    rpos = [(cx + 230 * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a)))
            for a in arc(len(right), -50, 50)]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="Map of my projects and posts">',
        f'<rect width="{W}" height="{H}" rx="14" fill="{c["bg"]}"/>',
        f'<g font-family="{FONT}">',
    ]
    # Lines: centre to each node, and project to its post.
    for x, y in lpos + rpos:
        parts.append(f'<path d="M{cx},{cy} Q{(cx + x) / 2},{cy} {x:.1f},{y:.1f}" fill="none" '
                     f'stroke="{c["line"]}" stroke-width="1.2"/>')
    for i, proj in enumerate(PROJECTS):
        if proj["post"] in post_slugs:
            (x1, y1), (x2, y2) = lpos[i], rpos[post_slugs.index(proj["post"])]
            parts.append(f'<path d="M{x1:.1f},{y1:.1f} C{cx},{y1 - 70:.1f} {cx},{y2 - 70:.1f} {x2:.1f},{y2:.1f}" '
                         f'fill="none" stroke="{c["gold"]}" stroke-opacity="0.35" stroke-width="1" '
                         f'stroke-dasharray="3 4"/>')
    # Centre.
    parts += [
        f'<circle cx="{cx}" cy="{cy}" r="34" fill="{c["gold"]}" fill-opacity="0.12"/>',
        f'<circle cx="{cx}" cy="{cy}" r="9" fill="{c["gold"]}"/>',
        f'<text x="{cx}" y="{cy + 30}" text-anchor="middle" font-size="14" font-weight="600" '
        f'fill="{c["text"]}">Ben Kelly</text>',
    ]
    for (x, y), label in zip(lpos, left):
        parts += [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{c["gold"]}"/>',
                  f'<text x="{x - 12:.1f}" y="{y + 4:.1f}" text-anchor="end" font-size="13" '
                  f'fill="{c["text"]}">{esc(label)}</text>']
    for (x, y), label in zip(rpos, right):
        parts += [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{c["silver"]}"/>',
                  f'<text x="{x + 12:.1f}" y="{y + 4:.1f}" font-size="13" fill="{c["text"]}">{esc(label)}</text>']
    parts += [
        f'<text x="22" y="30" font-size="12" fill="{c["gold"]}" letter-spacing="1.5">PROJECTS</text>',
        f'<text x="{W - 22}" y="30" text-anchor="end" font-size="12" fill="{c["silver"]}" letter-spacing="1.5">WRITING</text>',
        "</g></svg>",
    ]
    return "\n".join(parts) + "\n"


def listening_svg(theme, t):
    c = THEMES[theme]
    W, H = 880, 92
    if t["now"]:
        label = "NOW LISTENING"
    else:
        label = "LAST HEARD · " + t["when"].strftime("%d %b, %H:%M UTC").upper()
    bars = "".join(
        f'<rect x="{30 + i * 8}" y="{58 - h}" width="5" height="{h}" rx="1.5" fill="{c["gold"]}"/>'
        for i, h in enumerate([14, 26, 18, 32, 22])
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="{esc(label.title())}: {esc(t["track"])} by {esc(t["artist"])}">\n'
        f'<rect width="{W}" height="{H}" rx="14" fill="{c["bg"]}"/>\n'
        f'<g font-family="{FONT}">{bars}\n'
        f'<text x="90" y="30" font-size="11" letter-spacing="1.5" fill="{c["gold"]}">{esc(label)}</text>\n'
        f'<text x="90" y="54" font-size="18" font-weight="600" fill="{c["text"]}">{esc(trim(t["track"], 60))}</text>\n'
        f'<text x="90" y="76" font-size="14" fill="{c["silver"]}">{esc(trim(t["artist"], 70))}</text>\n'
        f'<text x="{W - 22}" y="{H - 14}" text-anchor="end" font-size="11" fill="{c["muted"]}">'
        f'heard by scrobSter</text>\n'
        f'</g></svg>\n'
    )


def picture(name, alt):
    return (f'<picture>\n  <source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">\n'
            f'  <img src="assets/{name}-light.svg" alt="{esc(alt)}" width="100%">\n</picture>')


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", help="JSON file with posts, gists, repos and track, instead of fetching")
    args = ap.parse_args()

    if args.fixtures:
        data = json.loads(Path(args.fixtures).read_text())
        if data.get("track") and data["track"].get("when"):
            data["track"]["when"] = datetime.fromisoformat(data["track"]["when"])
        sources = {k: (lambda v=v: v) for k, v in data.items()}
    else:
        sources = {"posts": blog_posts, "gists": gists, "repos": repos, "track": lastfm}

    def fetch(name):
        try:
            return sources[name]()
        except Exception as e:  # one broken source shouldn't stop the others
            print(f"skipping {name}: {e}", file=sys.stderr)
            return None

    text = README.read_text()
    ASSETS.mkdir(exist_ok=True)

    posts = fetch("posts")
    if posts:
        text = replace_section(text, "BLOG-POSTS", render_posts(posts))
        for theme in THEMES:
            (ASSETS / f"map-{theme}.svg").write_text(map_svg(theme, posts))
    g = fetch("gists")
    if g:
        text = replace_section(text, "GISTS", render_gists(g))
    r = fetch("repos")
    if r:
        text = replace_section(text, "REPOS", render_repos(r))
    t = fetch("track")
    if t:
        for theme in THEMES:
            (ASSETS / f"listening-{theme}.svg").write_text(listening_svg(theme, t))
        text = replace_section(text, "LISTENING", picture("listening", f"Last heard: {t['track']} by {t['artist']}"))

    README.write_text(text)
    print("done")


if __name__ == "__main__":
    main()
