#!/usr/bin/env python3
"""
SOURCE TEST — run this FIRST, before discover_ch.py.

Fetches each of the four Switzerland sources one at a time, prints the
raw HTML structure around anything that looks like a company entry, and
reports pass/fail per source. Nothing here writes a CSV or asserts
company data as final — this is purely diagnostic, same discipline as
the advisors_diagnostic.py step that caught the CRD field-name bug
earlier in this project.

Run this on GitHub Actions (real network access), read the output,
THEN fix discover_ch.py's parsers based on what's actually there —
not the other way around.
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (research; leadflow-ch-test/1.0)"}

SOURCES = {
    "startup.ch (medtech)": "https://www.startup.ch/medtech-startups",
    "startup.ch (biotech)": "https://www.startup.ch/biotech-startups",
    "medicalstartups.org (CH)": "https://medicalstartups.org/country/Switzerland/",
    "medicalstartups.org (Zurich)": "https://medicalstartups.org/location/Zurich/",
    "Seedtable (CH)": "https://www.seedtable.com/best-startups-in-switzerland",
    "Seedtable (health CH)": "https://www.seedtable.com/best-health-tech-startups-in-switzerland",
    "EU-Startups (search)": "https://www.eu-startups.com/?s=medtech+switzerland",
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

    html_len = len(r.text)
    print(f"  Response length: {html_len} chars")
    if html_len < 1000:
        print(f"  WARNING — suspiciously short response, may be a block page or redirect")
        print(f"  Body: {r.text[:500]}")
        return False

    soup = BeautifulSoup(r.text, "html.parser")

    # Show what heading tags actually contain — this is the ground truth
    # discover_ch.py's parsers need to match against, not a guess
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
        print("\n  FAIL — no usable structure found. Page may be JS-rendered")
        print("  (requests won't see JS-injected content) or genuinely empty.")
        return False

    print("\n  PASS — page fetched and has extractable structure.")
    print("  Compare the samples above against discover_ch.py's regex/parsing")
    print("  logic for this source and adjust to match reality.")
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
    print("Fix discover_ch.py's parser for each PASS source based on the actual")
    print("h2/h3/link samples printed above. Do NOT re-guess — use what's shown.")
    print("For any FAIL source, decide: retry with different URL, or drop it.")

if __name__ == "__main__":
    main()
