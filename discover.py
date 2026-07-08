#!/usr/bin/env python3
"""
LeadFlow — Multi-Source ICP Discovery
======================================
Extracts consultancy candidates from MULTIPLE scrapable public directories,
deduplicates, then hands off to enrichment + the four qualification filters.

Confirmed-scrapable sources (plain HTML, no bot-block, no JS wall):
  1. SimplerQMS         — device + pharma, per country (proven)
  2. Constares          — Med/RA/Quality consulting list, DE/AT/CH (fills Germany)
  3. Constares CRO      — CRO list, DE/AT/CH
  4. eudracon           — European Drug Regulatory Affairs Consultants members
  5. Umbrex             — top medical-device consulting firms

Excluded (bot-blocked or JavaScript-rendered — not free-scrapable, ToS wall):
  - Swiss Medtech       (bot detection)
  - Biotechgate / Swiss Life Sciences (JS/POST results)
  - MEDICA / COMPAMED   (JS, 5,300 unfiltered)
  These can be used as MANUAL reference lists, fed in via manual_seed.csv.

Wide extraction on purpose: these lists MIX device-regulatory with pharma / PV /
CRO firms. That's fine — the specialty filter (filters.py) strips non-ICP firms
downstream. Pull wide, filter tight.
"""

import csv
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LeadFlowResearchBot/0.2)"}
TIMEOUT = 25

# ---------------------------------------------------------------------------
# SOURCE 1 — SimplerQMS (per-country device + pharma directories)
# ---------------------------------------------------------------------------
SIMPLERQMS = {
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

# ---------------------------------------------------------------------------
# SOURCE 2/3 — Constares (DE/AT/CH). Plain-HTML article lists, each firm linked.
# ---------------------------------------------------------------------------
CONSTARES = [
    "https://www.constares.com/industry-information/medical-regulatory-affairs-consulting-services-list.html",
    "https://www.constares.com/industry-information/clinical-research-organizations-list.html",
]

# ---------------------------------------------------------------------------
# SOURCE 4 — eudracon members
# ---------------------------------------------------------------------------
EUDRACON = ["https://eudracon.eu/contact/our-members/"]

# ---------------------------------------------------------------------------
# SOURCE 5 — Umbrex medical-device firms
# ---------------------------------------------------------------------------
UMBREX = ["https://umbrex.com/resources/top-consulting-firms/top-medical-device-consulting-firms/"]


def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.text
        print(f"  [!] {url} -> HTTP {r.status_code}")
    except Exception as e:
        print(f"  [!] {url} -> {e}")
    return None


# ---------- SimplerQMS parser (name + description + website) ----------
def parse_simplerqms(html, country):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    headers = soup.find_all(["h2", "h3", "h4"])
    header_set = set(id(h) for h in headers)
    for i, header in enumerate(headers):
        name = header.get_text(strip=True)
        if not name or len(name) > 80:
            continue
        # skip section headers / prose, but NOT company names containing 'consulting'
        low = name.lower()
        if any(x in low for x in ["table of", "how to", "how ", "what ", "why ",
                                  "recommended", "in case", "list of", "areas of",
                                  "frequently", "conclusion", "introduction"]):
            continue
        if low.startswith(("the benefits", "choosing", "medical device consult",
                           "pharmaceutical consult", "top ")):
            continue
        # Walk forward through following elements until we hit the NEXT header
        desc, website = "", ""
        for el in header.next_elements:
            if getattr(el, "name", None) in ("h2", "h3", "h4") and id(el) in header_set:
                break
            if getattr(el, "name", None) == "p":
                desc += " " + el.get_text(" ", strip=True)
            if getattr(el, "name", None) == "a":
                href = el.get("href", "")
                if href.startswith("http") and "simplerqms" not in href:
                    website = href
        if len(desc.strip()) > 30:
            out.append({"company": name, "country": country, "website": website,
                        "description": desc.strip()[:600], "source": "SimplerQMS"})
    return out


# ---------- Constares parser (name - location list, each linked) ----------
COUNTRY_MAP = {"deutschland": "Germany", "österreich": "Austria", "osterreich": "Austria",
               "schweiz": "Switzerland", "germany": "Germany", "austria": "Austria",
               "switzerland": "Switzerland"}


def parse_constares(html, list_label):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        name = a.get_text(strip=True)
        if not name or len(name) < 3 or len(name) > 90:
            continue
        if not href.startswith("http") or "constares" in href:
            continue
        # the list line often continues after the anchor with " - City - Country"
        tail = ""
        if a.next_sibling:
            tail = str(a.next_sibling)
        line = (name + " " + tail).lower()
        country = ""
        for k, v in COUNTRY_MAP.items():
            if k in line:
                country = v
                break
        # CLEAN the name: strip trailing " - City - Country" that got baked in
        clean_name = re.split(r"\s*[-–]\s*", name)[0].strip()
        # if splitting nuked it (name legitimately has a dash), keep original if too short
        if len(clean_name) < 3:
            clean_name = name
        out.append({"company": clean_name, "country": country, "website": href,
                    "description": f"Listed in Constares {list_label} (DACH).",
                    "source": f"Constares ({list_label})"})
    return out


# ---------- Generic member-list parser (eudracon, umbrex) ----------
def parse_generic_links(html, source_name, country=""):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        name = a.get_text(strip=True)
        if not name or len(name) < 3 or len(name) > 90:
            continue
        if not href.startswith("http"):
            continue
        # Reject when the link text is itself a URL (Umbrex bug) or nav junk
        if name.lower().startswith(("http", "www.")) or "/" in name or ".com" in name.lower():
            continue
        if name.lower() in ("read more", "learn more", "visit", "website", "here",
                            "click here", "view", "details", "home", "contact"):
            continue
        if any(s in href for s in ["facebook", "twitter", "linkedin", "mailto",
                                   "youtube", "instagram", "umbrex.com", "eudracon"]):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"company": name, "country": country, "website": href,
                    "description": f"Listed by {source_name}.", "source": source_name})
    return out


def discover():
    all_firms = []

    print("[1] SimplerQMS ...")
    for country, urls in SIMPLERQMS.items():
        for u in urls:
            html = fetch(u)
            if html:
                found = parse_simplerqms(html, country)
                print(f"    {country}: {len(found)} from {u.split('/')[-2]}")
                all_firms += found
            time.sleep(1)

    print("[2] Constares (DE/AT/CH) ...")
    for u in CONSTARES:
        html = fetch(u)
        if html:
            label = "RA/Quality" if "regulatory" in u else "CRO"
            found = parse_constares(html, label)
            print(f"    {label}: {len(found)} firms")
            all_firms += found
        time.sleep(1)

    print("[3] eudracon ...")
    for u in EUDRACON:
        html = fetch(u)
        if html:
            found = parse_generic_links(html, "eudracon")
            print(f"    eudracon: {len(found)} firms")
            all_firms += found
        time.sleep(1)

    print("[4] Umbrex ...")
    for u in UMBREX:
        html = fetch(u)
        if html:
            found = parse_generic_links(html, "Umbrex")
            print(f"    Umbrex: {len(found)} firms")
            all_firms += found
        time.sleep(1)

    # Optional manual seed (Swiss Medtech / Biotechgate copied by hand)
    seed = OUTPUT_DIR / "manual_seed.csv"
    if seed.exists():
        with open(seed, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row.setdefault("source", "Manual seed")
                all_firms.append(row)
        print(f"[5] manual_seed.csv loaded")

    # ---- Deduplicate by normalized company name ----
    def norm(n):
        return re.sub(r"[^a-z0-9]", "", (n or "").lower())
    seen, deduped = {}, []
    for f in all_firms:
        k = norm(f["company"])
        if not k:
            continue
        if k in seen:
            # merge: keep the richer description / fill website
            if len(f.get("description", "")) > len(seen[k].get("description", "")):
                seen[k]["description"] = f["description"]
            if not seen[k].get("website") and f.get("website"):
                seen[k]["website"] = f["website"]
            if not seen[k].get("country") and f.get("country"):
                seen[k]["country"] = f["country"]
            seen[k]["source"] = seen[k]["source"] + " + " + f["source"]
            continue
        seen[k] = f
        deduped.append(f)

    # write raw discovery
    out = OUTPUT_DIR / "icp_discovered.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["company", "country", "website", "description", "source"])
        w.writeheader()
        for row in deduped:
            w.writerow({k: row.get(k, "") for k in ["company", "country", "website", "description", "source"]})

    print(f"\nDISCOVERED {len(deduped)} unique firms across sources -> {out}")
    return deduped


if __name__ == "__main__":
    discover()
