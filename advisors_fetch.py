#!/usr/bin/env python3
"""
US Financial Advisors — Discovery (SEC IAPD, free official data)
================================================================
SEPARATE PROJECT — unrelated to the LeadFlow ICP pipeline.

Pulls investment-adviser FIRMS + named representatives from the SEC's official
public IAPD API (the same endpoint adviserinfo.sec.gov uses). Free, no login.

One-state test: set STATE below. Produces advisors_<state>.csv with:
  firm, advisor_name, crd, firm_crd, city, state, website (if present)

NOTE: SEC data does NOT include email/phone — those are added in the separate
enrich step (enrich_contacts.py) by visiting firm websites. This module only
does the free official discovery.
"""

import csv
import json
import time
from pathlib import Path

import requests

STATE = "WY"  # <-- one-state test (Wyoming = small, fast). Change to test others.
OUT = Path(f"us_advisors_{STATE}.csv")

HEADERS = {"User-Agent": "Mozilla/5.0 (research; advisor-discovery/0.1)"}

# SEC IAPD public search API (used by adviserinfo.sec.gov). Firm search by state.
# hits (firms) come back as JSON. This is the official public endpoint.
FIRM_SEARCH = "https://api.adviserinfo.sec.gov/search/firm"
IND_SEARCH = "https://api.adviserinfo.sec.gov/search/individual"


def fetch_firms_by_state(state, max_pages=50):
    """Page through firm search filtered by state."""
    firms = []
    for page in range(max_pages):
        params = {
            "query": "",           # empty query
            "state": state,
            "type": "Firm",
            "start": page * 10,
        }
        try:
            r = requests.get(FIRM_SEARCH, params=params, headers=HEADERS, timeout=25)
            if r.status_code != 200:
                print(f"  [!] firm page {page} HTTP {r.status_code}")
                break
            data = r.json()
        except Exception as e:
            print(f"  [!] firm page {page} error: {e}")
            break

        hits = (data.get("hits", {}) or {}).get("hits", [])
        if not hits:
            break
        # DIAGNOSTIC: on the very first hit, print the real field names once
        if page == 0 and hits:
            first_src = hits[0].get("_source", hits[0])
            print(f"  [FIELDS] {list(first_src.keys())}")
            print(f"  [SAMPLE] {json.dumps(first_src)[:400]}")
        for h in hits:
            src = h.get("_source", h)
            firms.append({
                "firm": src.get("firm_name") or src.get("org_name") or "",
                "firm_crd": (src.get("firm_crd") or src.get("crd") or src.get("firm_source_id")
                             or src.get("firm_ia_full_source_id") or src.get("source_id") or ""),
                "city": src.get("firm_city") or src.get("city") or "",
                "state": src.get("firm_state") or state,
                "website": "",  # filled during enrichment
            })
        print(f"  firms page {page}: +{len(hits)} (total {len(firms)})")
        time.sleep(0.5)
    return firms


def main():
    print(f"=== SEC IAPD discovery — state: {STATE} ===\n")
    firms = fetch_firms_by_state(STATE)

    # dedupe by firm_crd
    seen, deduped = set(), []
    for f in firms:
        k = f["firm_crd"] or f["firm"].lower()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(f)

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["firm", "firm_crd", "city", "state", "website"])
        w.writeheader()
        w.writerows(deduped)

    print(f"\nDISCOVERED {len(deduped)} firms in {STATE} -> {OUT}")
    print("Next: run enrich_contacts.py to pull website + email/phone where public.")


if __name__ == "__main__":
    main()
