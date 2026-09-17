#!/usr/bin/env python3
"""Scrape a website into knowledge-base text, stripping shared nav/footer boilerplate.

Usage:
    python scrape_site.py https://your-site.org [--out kb/pages_raw.json]

It discovers same-domain links from the home page, fetches each page, removes lines
that repeat across many pages (nav/header/footer), and writes the cleaned text per
page to a JSON file. Review that output and curate it into kb/knowledge_base.md
(the file that gets embedded into the assistant's system prompt).

Requires: requests, beautifulsoup4, lxml
"""
import sys, json, time, argparse
from collections import Counter
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "site-scraper"}


def get_text(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
    except Exception as e:
        return None, str(e)
    s = BeautifulSoup(r.text, "lxml")
    for tag in s(["script", "style", "noscript"]):
        tag.decompose()
    lines = [ln.strip() for ln in s.get_text("\n").splitlines() if ln.strip()]
    return r.status_code, "\n".join(lines)


def discover_links(base):
    r = requests.get(base, headers=HEADERS, timeout=30)
    soup = BeautifulSoup(r.text, "lxml")
    host = urlparse(base).netloc.replace("www.", "")
    links = {base.rstrip("/")}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "tel:")):
            continue
        full = urljoin(base, href).split("#")[0].rstrip("/")
        if urlparse(full).netloc.replace("www.", "") == host:
            links.add(full)
    return sorted(links)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    ap.add_argument("--out", default="pages_raw.json")
    ap.add_argument("--delay", type=float, default=0.2)
    args = ap.parse_args()

    urls = discover_links(args.base_url)
    print("discovered %d pages" % len(urls))
    pages = {}
    for u in urls:
        st, txt = get_text(u)
        if st == 200 and txt:
            pages[u] = txt
        time.sleep(args.delay)
    print("fetched %d pages" % len(pages))

    # boilerplate = lines appearing on many pages
    counts = Counter()
    for txt in pages.values():
        for ln in set(txt.splitlines()):
            counts[ln] += 1
    n = len(pages)
    boiler = {ln for ln, c in counts.items() if c >= max(3, int(n * 0.5))}

    cleaned = {}
    for u, txt in pages.items():
        cleaned[u] = "\n".join(ln for ln in txt.splitlines() if ln not in boiler).strip()

    with open(args.out, "w") as f:
        json.dump(cleaned, f, indent=1, ensure_ascii=False)
    print("wrote %s (%d pages, %d boilerplate lines removed)" % (args.out, len(cleaned), len(boiler)))
    print("Now review it and curate the important facts into kb/knowledge_base.md")


if __name__ == "__main__":
    main()
