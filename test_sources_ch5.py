#!/usr/bin/env python3
"""
SOURCE TEST — ROUND 5, fixing the 4 messy sources from round 4:
University of Basel, startupticker.ch, BioAlps, BaseLaunch.

These loaded fine but round 4's simple check only found menu items, not
real company names. Two likely reasons: (1) the real company list is
further down the page than the first batch of links, or (2) it's loaded
by JavaScript after the page loads, which a simple fetch can't see.

This test checks both possibilities: looks at ALL links on the page (not
just the first 15), and checks whether the page mentions JavaScript being
required (a sign we're missing JS-loaded content).
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (research; leadflow-ch-test5/1.0)"}

SOURCES = {
    "Uni Basel Our Start-ups": "https://www.unibas.ch/en/University/Innovation/Propelling-Grants/Our-Start-ups.html",
    "startupticker.ch (digital health)": "https://www.startupticker.ch/en/news?tag=Digital+health",
    "BioAlps": "https://bioalps.org/venture-leaders-medtech-2026/",
    "BaseLaunch portfolio": "https://baselaunch.ch/portfolio/",  # switched to the actual portfolio page, not /news/
}

SKIP_WORDS = [
    "skip to", "menu", "search", "login", "register", "forgot", "contact",
    "about", "news", "home", "further information", "quick links",
    "faculties", "students", "lecturers", "donors", "locations", "footer",
    "language", "services", "department", "alumni", "laboratories",
    "collaboration", "domains", "launchpad", "catalyst", "calendar",
    "assets", "team", "supporters", "cooperations", "faq", "join us",
    "impressum", "submit", "editorial", "guest column", "media house",
    "studies", "degree programs", "application", "dates", "ukraine",
    "social media", "uni nova", "awards", "events", "sitemap", "staffnet",
    "student portal", "eth zurich", "education", "innovation", "schools",
    "campus", "mission", "organization", "media center", "business",
    "community", "the health valley", "perspectives", "work with us",
    "our offering", "apply", "success stories", "20 years",
]

def check_javascript_dependency(html):
    lowered = html.lower()
    if "requires javascript" in lowered or "enable javascript" in lowered or "please turn on javascript" in lowered:
        return True
    return False

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

    if check_javascript_dependency(r.text):
        print("  WARNING: this page appears to require JavaScript to show real")
        print("  content. A simple fetch cannot see JS-loaded company listings.")
        print("  This source likely needs a different tool (browser automation)")
        print("  to read properly, not a plain page fetch.")

    soup = BeautifulSoup(r.text, "html.parser")
    all_links = soup.find_all("a", href=True)
    print(f"  Total links on page: {len(all_links)}")

    candidates = []
    for a in all_links:
        text = a.get_text(strip=True)
        href = a["href"]
        if not text or len(text) < 3 or len(text) > 90:
            continue
        if any(w in text.lower() for w in SKIP_WORDS):
            continue
        if href.startswith("#") or href.startswith("tel:") or href.startswith("mailto:") or "javascript:" in href:
            continue
        candidates.append((text, href, a.parent.name if a.parent else "?"))

    print(f"  Candidate company-like links (after filtering): {len(candidates)}")
    print(f"  ALL candidates (not just first 15) (tag, text -> href):")
    for text, href, tag in candidates:
        print(f"    [{tag}] {text!r} -> {href}")

def main():
    for name, url in SOURCES.items():
        inspect(name, url)

if __name__ == "__main__":
    main()
