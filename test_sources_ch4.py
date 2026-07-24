#!/usr/bin/env python3
"""
SOURCE TEST — ROUND 4, deeper look at the 10 confirmed-working sources
from round 3, to find exactly where real company names sit on each page.

Same purpose as test_sources_ch2.py, applied to the new batch. No CSV
output — diagnostic only, so the real collection script can be written
against confirmed reality, not a guess.
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (research; leadflow-ch-test4/1.0)"}

SOURCES = {
    "Innosuisse funded startups": "https://www.innosuisse.admin.ch/en/approved-start-up-innovation-projects",
    "ETH Zurich spin-offs (BSSE)": "https://bsse.ethz.ch/department/spin-offs.html",
    "EPFL startups": "https://www.epfl.ch/innovation/startup/discover-our-startups/",
    "EPFL startups-in-creation": "https://www.epfl.ch/innovation/startup/discover-our-startups/epfl-startup-in-creation/",
    "Uni Basel Our Start-ups": "https://www.unibas.ch/en/University/Innovation/Propelling-Grants/Our-Start-ups.html",
    "startupticker.ch (digital health)": "https://www.startupticker.ch/en/news?tag=Digital+health",
    "BioAlps": "https://bioalps.org/venture-leaders-medtech-2026/",
    "BaseLaunch news/portfolio": "https://baselaunch.ch/news/",
}

# Words that show up in menus/nav/generic links — used to filter noise
# out of the "candidate" list so real company names are easier to spot
SKIP_WORDS = [
    "skip to", "menu", "search", "login", "contact", "about", "news",
    "home", "further information", "quick links", "faculties", "students",
    "lecturers", "donors", "locations", "footer", "language", "services",
    "department", "alumni", "laboratories", "collaboration", "domains",
    "launchpad", "catalyst", "regional programs", "why ", "how does",
    "who is", "what makes", "week ", "post-accelerator", "principal",
    "foundation", "editorial", "partners", "tel:", "fax:", "mailto:",
]

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
        if href.startswith("#") or href.startswith("tel:") or href.startswith("mailto:"):
            continue
        candidates.append((text, href, a.parent.name if a.parent else "?"))

    print(f"  Candidate company-like links: {len(candidates)}")
    print(f"  First 15 (tag, text -> href):")
    for text, href, tag in candidates[:15]:
        print(f"    [{tag}] {text!r} -> {href}")

def main():
    for name, url in SOURCES.items():
        inspect(name, url)
    print("\n\nUse the [tag] shown before each real company entry as the")
    print("container pattern for discover_ch.py, same as done for Seedtable.")

if __name__ == "__main__":
    main()
