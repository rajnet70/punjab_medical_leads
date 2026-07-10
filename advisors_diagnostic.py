#!/usr/bin/env python3
"""
DIAGNOSTIC — shows exactly what the SEC brochure path does for 5 firms.
Prints: the detail API response, the brochure URL found, the download result.
This tells us the REAL structure so we stop guessing.
"""
import csv, json, re, io
import requests

HEADERS = {"User-Agent":"Mozilla/5.0 (research; advisor-diag/1.0)"}
DETAIL = "https://api.adviserinfo.sec.gov/search/firm/{crd}"

def fetch(url, binary=False):
    try:
        r=requests.get(url,headers=HEADERS,timeout=20)
        return (r.status_code, r.content if binary else r.text)
    except Exception as e:
        return (None, str(e))

rows = list(csv.DictReader(open("us_advisors_WY.csv")))[:5]
print(f"Diagnosing {len(rows)} firms\n"+"="*60)

for f in rows:
    crd = f.get("firm_crd","")
    name = f.get("firm","")
    print(f"\n### {name} (CRD: {crd})")

    # 1. Call the detail endpoint, show what comes back
    status, body = fetch(DETAIL.format(crd=crd))
    print(f"  detail API status: {status}")
    if status != 200:
        print(f"  BODY (first 200 chars): {str(body)[:200]}")
        continue

    # 2. Show the actual JSON structure - what keys exist
    try:
        d = json.loads(body)
        # navigate to source
        src = d
        if isinstance(d,dict) and "hits" in d:
            hits = d.get("hits",{}).get("hits",[])
            print(f"  hits found: {len(hits)}")
            src = hits[0].get("_source",{}) if hits else {}
        if isinstance(src,dict):
            print(f"  top-level keys: {list(src.keys())[:30]}")
        # 3. Find ANY url in the whole blob
        blob = json.dumps(src)
        urls = re.findall(r'https?://[^\s"\\]+', blob)
        print(f"  URLs in record ({len(urls)}):")
        for u in urls[:8]:
            print(f"     {u}")
    except Exception as e:
        print(f"  JSON parse error: {e}")
        print(f"  raw body (first 300): {body[:300]}")

print("\n"+"="*60)
print("Paste this whole output back so I can see the real SEC structure.")
