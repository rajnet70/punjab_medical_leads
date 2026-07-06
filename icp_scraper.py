#!/usr/bin/env python3
"""
LeadFlow — ICP Prospecting Pipeline
Finds LeadFlow's OWN ideal clients: boutique regulatory / QA consultancies
in the medtech / pharma space, who would buy LeadFlow's market intelligence.

Source: SimplerQMS public consultant directories (per country).
Verdict: clean, structured, public. One page = full country list.

This is the DISCOVERY + ICP-SCORING layer. Runs adjacent to manual LinkedIn /
Sales Navigator outreach: it hands you a ranked shortlist; you do the human outreach.

Enrichment (founder name, published contact, size) is a separate later step —
placeholders are left in the output for it.
"""

import csv
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# --- Full SimplerQMS directory set (medical-device AND pharmaceutical, all countries) ---
# Both directory types are included because regulatory/QA consultancies often serve both,
# and the two lists contain largely DIFFERENT firms — roughly doubling the yield.
SOURCES = {
    "Switzerland":  ["https://simplerqms.com/consultants/medical-device-switzerland/",
                     "https://simplerqms.com/consultants/pharmaceutical-switzerland/"],
    "UK & Ireland": ["https://simplerqms.com/consultants/medical-device-consulting-firms/",
                     "https://simplerqms.com/consultants/pharmaceutical-consulting-uk-ie/"],
    "Denmark":      ["https://simplerqms.com/consultants/medical-device-denmark/",
                     "https://simplerqms.com/consultants/pharmaceutical-denmark/"],
    "Netherlands":  ["https://simplerqms.com/consultants/medical-device-netherlands/",
                     "https://simplerqms.com/consultants/pharmaceutical-netherlands/"],
    "Sweden":       ["https://simplerqms.com/consultants/medical-device-sweden/",
                     "https://simplerqms.com/consultants/pharmaceutical-sweden/"],
    "Austria":      ["https://simplerqms.com/consultants/top-pharmaceutical-consulting-firms-in-at/"],
}

OUTPUT_DIR = Path("output")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LeadFlowResearchBot/0.1)"}

# --- ICP scoring keywords (applied to each firm's description) ---
STARTUP_SIGNALS  = ["start-up", "startup", "start up", " sme", "smes", "aspiring", "small and medium",
                    "small to medium", "small-", "cost-effective"]
BOUTIQUE_SIGNALS = ["specialist", "specialized", "specialised", "boutique", "personalized",
                    "personalised", "tailored", "hands-on", "hands on", "team of experts",
                    "independent", "small firm", "small consultancy"]
REG_SIGNALS      = ["regulatory", "mdr", "ivdr", "iso 13485", "quality assurance", "ce mark",
                    "quality management", "regulatory affairs", "qms", "qa/ra", "ra/qa"]
LARGE_SIGNALS    = ["125 years", "global organizations", "global organisations", "worldwide",
                    "multinational", "90 employees", "employees working", "leading consultancy companies",
                    "20 years", "over 20 years", "large scale"]


def fetch(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_directory(html: str, country: str) -> list[dict]:
    """
    Each consultancy: a name (in an <h3> or bold heading) followed by a description
    paragraph and a 'Visit site' link. Anchor on the 'Visit site' links (reliable),
    then read backwards for the name and description.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # 'Visit site' links are the reliable anchor for each real entry.
    for link in soup.find_all("a", string=re.compile(r"visit site", re.I)):
        website = link.get("href", "")
        if not website or "simplerqms.com" in website:
            continue

        # The description is the text just before the link (its paragraph).
        desc = ""
        p = link.find_parent("p") or link.find_previous("p")
        if p:
            desc = p.get_text(" ", strip=True)
            desc = re.sub(r"\s*Visit site\s*$", "", desc, flags=re.I).strip()

        # The name is the nearest preceding heading (h2/h3/strong).
        name = ""
        heading = link.find_previous(["h2", "h3", "h4", "strong", "b"])
        if heading:
            name = heading.get_text(strip=True)
        # Fallback: first few words of the description up to a verb
        if not name and desc:
            name = desc.split(" is ")[0].split(" provides ")[0].split(" offers ")[0][:50].strip()

        key = name.lower().strip()
        if not name or key in seen or len(desc) < 40:
            continue
        seen.add(key)

        companies.append({
            "company": name,
            "country": country,
            "description": desc[:400],
            "website": website,
            "source": "SimplerQMS directory",
        })

    return companies


def score_icp(c: dict) -> dict:
    text = c["description"].lower()
    startup  = any(s in text for s in STARTUP_SIGNALS)
    boutique = any(s in text for s in BOUTIQUE_SIGNALS)
    reg      = any(s in text for s in REG_SIGNALS)
    large    = any(s in text for s in LARGE_SIGNALS)

    score = 0
    if reg: score += 1
    if boutique: score += 1
    if startup: score += 2      # startup/SME-facing is the strongest ICP signal
    if large: score -= 2

    fit = "STRONG" if score >= 3 else ("GOOD" if score >= 1 else "QUALIFY")

    signals = []
    if startup:  signals.append("startup/SME-facing")
    if boutique: signals.append("boutique/specialist")
    if reg:      signals.append("regulatory/QA focus")
    if large:    signals.append("(larger firm — de-prioritised)")

    c["icp_fit"] = fit
    c["icp_signals"] = ", ".join(signals) if signals else "—"
    c["founder"] = "(enrich from site)"
    c["public_contact"] = "(enrich from site)"
    return c


def scrape(countries=None, limit_per_country=None) -> list[dict]:
    countries = countries or list(SOURCES.keys())
    all_rows, seen_global = [], set()
    for country in countries:
        for url in SOURCES.get(country, []):
            print(f"[SimplerQMS] {country}: {url}")
            try:
                html = fetch(url)
            except Exception as e:
                print(f"  ! failed: {e}")
                continue
            rows = [score_icp(r) for r in parse_directory(html, country)]
            # de-dupe across the two directories per country
            fresh = []
            for r in rows:
                k = (r["company"].lower(), country)
                if k not in seen_global:
                    seen_global.add(k); fresh.append(r)
            print(f"  found {len(fresh)} new consultancies")
            if limit_per_country:
                fresh = fresh[:limit_per_country]
            all_rows.extend(fresh)
            time.sleep(2)
    return all_rows


def write_csv(rows: list[dict], path: Path):
    path.parent.mkdir(exist_ok=True)
    fields = ["company", "country", "icp_fit", "icp_signals", "description",
              "founder", "public_contact", "website", "source"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    rows = scrape()   # all target countries
    order = {"STRONG": 0, "GOOD": 1, "QUALIFY": 2}
    rows.sort(key=lambda r: (order.get(r["icp_fit"], 3), r["country"]))
    write_csv(rows, OUTPUT_DIR / "icp_consultancies.csv")

    # summary
    from collections import Counter
    by_fit = Counter(r["icp_fit"] for r in rows)
    by_country = Counter(r["country"] for r in rows)
    print(f"\n=== {len(rows)} consultancies found ===")
    print("By fit:    ", dict(by_fit))
    print("By country:", dict(by_country))
    print("\nSTRONG-fit prospects (your priority outreach list):")
    for r in rows:
        if r["icp_fit"] == "STRONG":
            print(f"  {r['company']} ({r['country']}) — {r['icp_signals']}")


if __name__ == "__main__":
    main()
