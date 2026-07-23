#!/usr/bin/env python3
"""
SOURCE TEST — ROUND 3, new sources found in deep research pass.

Same purpose as test_sources_ch.py and test_sources_ch2.py: check each
source actually loads and has real, extractable company data, before
writing any collection logic against it. Nothing here is guessed.
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (research; leadflow-ch-test3/1.0)"}

SOURCES = {
    # Government / institutional — expected highest reliability
    "Innosuisse funded startups": "https://www.innosuisse.admin.ch/en/approved-start-up-innovation-projects",
    "ETH Zurich spin-offs (BSSE)": "https://bsse.ethz.ch/department/spin-offs.html",
    "EPFL startups": "https://www.epfl.ch/innovation/startup/discover-our-startups/",
    "EPFL startups-in-creation": "https://www.epfl.ch/innovation/startup/discover-our-startups/epfl-startup-in-creation/",
    "Uni Basel spin-offs (Biomedical Eng)": "https://dbe.unibas.ch/en/innovation/spin-offs/",
    "Uni Basel Our Start-ups": "https://www.unibas.ch/en/University/Innovation/Propelling-Grants/Our-Start-ups.html",
    "Swiss Medtech Day company list (PDF)": "https://www.swiss-medtech.ch/sites/default/files/2026-06/SMD26_Companies_260610.pdf",

    # News / industry association
    "startupticker.ch (digital health)": "https://www.startupticker.ch/en/news?tag=Digital+health",
    "Swiss Biotech Association directory": "https://www.swissbiotech.org/companies/",
    "BioAlps": "https://bioalps.org/venture-leaders-medtech-2026/",
    "DayOne accelerator": "https://www.dayone.swiss/accelerator/",

    # Accelerator portfolios
    "BaseLaunch news/portfolio": "https://baselaunch.ch/news/",
}

def test_source(name, url):
    print(f"\n{'='*60}")
    print(f"TESTING: {name}")
    print(f"URL: {url}")
    print('='*60)
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except Exception as e:
        print(f"  FAIL — request error: {e}")
        return False

    print(f"  HTTP status: {r.status_code}")
    if r.status_code != 200:
        print(f"  FAIL — non-200 response")
        print(f"  First 300 chars of body: {r.text[:300]}")
        return False

    content_type = r.headers.get("Content-Type", "")
    print(f"  Content-Type: {content_type}")

    if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
        print(f"  PDF file detected — length: {len(r.content)} bytes")
        print(f"  PASS — file downloaded successfully. Needs a PDF text-extraction")
        print(f"  step (different from HTML parsing) to pull company names out.")
        return True

    html_len = len(r.text)
    print(f"  Response length: {html_len} chars")
    if html_len < 1000:
        print(f"  WARNING — suspiciously short response, may be a block page")
        print(f"  Body: {r.text[:500]}")
        return False

    soup = BeautifulSoup(r.text, "html.parser")
    h2s = [h.get_text(strip=True) for h in soup.find_all("h2")][:5]
    h3s = [h.get_text(strip=True) for h in soup.find_all("h3")][:5]
    links_with_text = [(a.get_text(strip=True)[:80], a.get("href", "")[:60])
                        for a in soup.find_all("a", href=True) if len(a.get_text(strip=True)) > 15][:8]

    print(f"\n  First 5 <h2> tags: {h2s}")
    print(f"  First 5 <h3> tags: {h3s}")
    print(f"\n  First 8 substantial links (text, href):")
    for text, href in links_with_text:
        print(f"    - {text!r} -> {href}")

    if not h2s and not h3s and not links_with_text:
        print("\n  FAIL — no usable structure found.")
        return False

    print("\n  PASS — page fetched and has extractable structure.")
    return True

def main():
    results = {}
    for name, url in SOURCES.items():
        results[name] = test_source(name, url)

    print(f"\n\n{'='*60}")
    print("SUMMARY")
    print('='*60)
    for name, passed in results.items():
        print(f"  {'PASS' if passed else 'FAIL':6} — {name}")

    passed_count = sum(results.values())
    print(f"\n{passed_count}/{len(results)} sources returned usable structure.")

if __name__ == "__main__":
    main()
