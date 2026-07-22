#!/usr/bin/env python3
"""
DEEPER SOURCE TEST — round 2.

Round 1 showed that 5 of 7 pages load fine, but company names live in
plain links, not headline tags — so the first parsing logic looked in
the wrong place and returned nothing. This test looks specifically at
the link structure around real company names to find the actual pattern
to match, before rewriting the real collection script.

Still no CSV output — this is diagnostic only.
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (research; leadflow-ch-test2/1.0)"}

SOURCES = {
    "medicalstartups.org (CH)": "https://medicalstartups.org/country/Switzerland/",
    "Seedtable (CH)": "https://www.seedtable.com/best-startups-in-switzerland",
    "Seedtable (health CH)": "https://www.seedtable.com/best-health-tech-startups-in-switzerland",
    "EU-Startups (search)": "https://www.eu-startups.com/?s=medtech+switzerland",
}

def inspect(name, url):
    print(f"\n{'='*60}")
    print(f"INSPECTING: {name}")
    print('='*60)
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except Exception as e:
        print(f"  request error: {e}")
        return
    if r.status_code != 200:
        print(f"  non-200: {r.status_code}")
        return

    soup = BeautifulSoup(r.text, "html.parser")

    # Look at every link that points to a company-shaped URL pattern
    # (i.e. not a nav/category link) and show its surrounding context
    all_links = soup.find_all("a", href=True)
    print(f"  Total links on page: {len(all_links)}")

    candidate_links = []
    for a in all_links:
        text = a.get_text(strip=True)
        href = a["href"]
        # skip obvious nav/category/pagination links
        if not text or len(text) < 3 or len(text) > 60:
            continue
        skip_words = ["category", "country", "location", "database", "sign", "login",
                      "password", "sourcing", "briefing", "faq", "explore", "related",
                      "city", "top ", "market landscape"]
        if any(w in text.lower() for w in skip_words):
            continue
        candidate_links.append((text, href))

    print(f"  Candidate company-like links found: {len(candidate_links)}")
    print(f"  First 15 candidates (text -> href):")
    for text, href in candidate_links[:15]:
        # show the parent tag type too — tells us the actual DOM shape
        parent_tag = None
        for a in all_links:
            if a.get_text(strip=True) == text and a["href"] == href:
                parent_tag = a.parent.name if a.parent else "?"
                break
        print(f"    [{parent_tag}] {text!r} -> {href}")

def main():
    for name, url in SOURCES.items():
        inspect(name, url)
    print("\n\nUse the [tag] shown before each entry — that's the real container")
    print("to search for in discover_ch.py, replacing the h2/h3 guess.")

if __name__ == "__main__":
    main()
