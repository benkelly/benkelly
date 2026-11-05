#!/usr/bin/env python3
"""Put the latest blog posts into README.md, between the BLOG-POSTS markers.

Usage: python3 scripts/update_posts.py [--feed URL] [--count N]

Reads the blog's RSS feed, keeps only posts on blog.benjamin.ie (the feed
also lists gists), newest first. Standard library only.
"""
import argparse
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"
START, END = "<!-- BLOG-POSTS:START -->", "<!-- BLOG-POSTS:END -->"


def posts(feed_xml, count):
    items = []
    for item in ET.fromstring(feed_xml).iter("item"):
        link = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        when = item.findtext("pubDate")
        if not link.startswith("https://blog.benjamin.ie/blog/") or not title or not when:
            continue
        if link.rstrip("/").endswith("/hello-world"):
            continue
        items.append((parsedate_to_datetime(when), title, link))
    items.sort(reverse=True)
    return items[:count]


def render(items):
    # Escape characters that would break a markdown link.
    esc = lambda s: re.sub(r"([\[\]])", r"\\\1", s)
    return "\n".join(f"- [{esc(t)}]({l}) · {d:%d %b %Y}" for d, t, l in items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", default="https://blog.benjamin.ie/api/rss")
    ap.add_argument("--count", type=int, default=5)
    args = ap.parse_args()

    req = urllib.request.Request(args.feed, headers={"User-Agent": "benkelly-profile-readme"})
    with urllib.request.urlopen(req, timeout=30) as r:
        items = posts(r.read(), args.count)
    if not items:
        sys.exit("No blog posts found in the feed; leaving README.md alone.")

    text = README.read_text()
    if START not in text or END not in text:
        sys.exit("README.md is missing the BLOG-POSTS markers.")
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    new = f"{before}{START}\n{render(items)}\n{END}{after}"
    if new != text:
        README.write_text(new)
        print(f"Updated README.md with {len(items)} posts.")
    else:
        print("README.md already up to date.")


if __name__ == "__main__":
    main()
