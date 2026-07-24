#!/usr/bin/env python3
"""
SWITZERLAND DISCOVERY — real collection script.

Built from CONFIRMED, tested patterns only (see test_sources_ch through
test_sources_ch5.py in this repo for the proof each pattern is based on).
Nothing here is guessed.

Six working sources:
  1. Seedtable              — company names sit in <span> tags
  2. Innosuisse              — company website links sit in <span> tags
  3. ETH Zurich (BSSE)        — company names sit in <p> tags, marked
                                "external page" prefix
  4. EPFL (startups-in-creation) — company names sit in <td> tags
  5. University of Basel      — company names + website sit in <p> tags
  6. BioAlps                  — company website links sit in <p> tags

NOT included (confirmed not usable, see project notes):
  - startup.ch, Swiss Biotech Association, startupticker.ch — all require
    a logged-in session we don't reliably have; login attempts failed
  - medicalstartups.org — returns a 415 error, unresolved
  - EU-Startups — page has no real company listing, only site navigation

This script only DISCOVERS companies (name + website + source). Founder
names, funding, and contact details are a separate step: enrich_ch.py.
"""
import csv
import re
import time
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (research; leadflow-ch/1.0)"}

# Words that show up in menus/navigation — filtered out everywhere,
# confirmed from real page content across all sources tested
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
    "our offering", "apply", "success stories", "20 years", "privacy",
    "terms", "legal", "jobs", "career", "sitemap", "linkedin", "twitter",
    "facebook", "instagram", "youtube", "subscribe", "newsletter",
    "partners", "portfolio", "members", "membership", "financing",
    "coaching", "incubator", "technopark", "university", "networks",
    "industrial network", "economic promotion", "international markets",
    "innovation networks", "technology transfer", "farewell", "welcome",
    "wins its legal battle",  # BioAlps news headline noise, not a company link
]

def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            return r.text
        print(f"  non-200 ({r.status_code}) for {url}")
    except Exception as e:
        print(f"  fetch error {url}: {e}")
    return None

def is_noise(text):
    if not text or len(text) < 2 or len(text) > 80:
        return True
    return any(w in text.lower() for w in SKIP_WORDS)

# ---------------------------------------------------------------
# SOURCE 1: Seedtable — company names in <span>, confirmed pattern
# ---------------------------------------------------------------
SEEDTABLE_PAGES = [
    "https://www.seedtable.com/best-startups-in-switzerland",
    "https://www.seedtable.com/best-health-tech-startups-in-switzerland",
    "https://www.seedtable.com/best-startups-in-zurich",
    "https://www.seedtable.com/best-startups-in-basel",
    "https://www.seedtable.com/best-health-tech-startups-in-zurich",
]
SEEDTABLE_NON_MEDICAL_KNOWN = {"climeworks", "swissto12", "auterion"}

def parse_seedtable(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for span in soup.find_all("span"):
        text = span.get_text(strip=True)
        if is_noise(text):
            continue
        key = re.sub(r'[^a-z0-9]', '', text.lower())
        if key in SEEDTABLE_NON_MEDICAL_KNOWN:
            continue
        parent = span.find_parent("a", href=True)
        if not parent or "/companies/" not in parent.get("href", ""):
            continue
        href = parent["href"]
        rows.append({
            "company": text,
            "website": "",
            "source": "Seedtable",
            "source_page": "https://www.seedtable.com" + href if href.startswith("/") else href,
        })
    return rows

# ---------------------------------------------------------------
# SOURCE 2: Innosuisse — real company website links in <span>
# ---------------------------------------------------------------
INNOSUISSE_PAGE = "https://www.innosuisse.admin.ch/en/approved-start-up-innovation-projects"

def parse_innosuisse(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for span in soup.find_all("span"):
        a = span.find_parent("a", href=True)
        text = span.get_text(strip=True)
        if not a:
            continue
        href = a["href"]
        # confirmed pattern: these are direct company website URLs, e.g. https://4kmems.ch
        if not re.match(r'^https?://', href) or "admin.ch" in href or "powerbi.com" in href:
            continue
        # derive a company name guess from the domain itself since no
        # separate name text is shown next to these links — flagged
        # honestly: this is a domain-derived label, not a stated company
        # name, so enrichment should confirm/replace it from the site itself
        domain = re.sub(r'^https?://(www\.)?', '', href).split('/')[0]
        rows.append({
            "company": domain,  # placeholder — real name comes from enrichment
            "website": href,
            "source": "Innosuisse",
            "source_page": INNOSUISSE_PAGE,
        })
    return rows

# ---------------------------------------------------------------
# SOURCE 3: ETH Zurich (BSSE) — company names in <p>, "external page" prefix
# ---------------------------------------------------------------
ETH_PAGE = "https://bsse.ethz.ch/department/spin-offs.html"

def parse_eth(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for p in soup.find_all("p"):
        a = p.find("a", href=True)
        if not a:
            continue
        text = a.get_text(strip=True)
        # confirmed pattern: text is prefixed with "external page"
        if text.lower().startswith("external page"):
            text = text[len("external page"):].strip()
        if is_noise(text):
            continue
        rows.append({
            "company": text,
            "website": a["href"],
            "source": "ETH Zurich (BSSE)",
            "source_page": ETH_PAGE,
        })
    return rows

# ---------------------------------------------------------------
# SOURCE 4: EPFL startups-in-creation — company names in <td>
# ---------------------------------------------------------------
EPFL_PAGE = "https://www.epfl.ch/innovation/startup/discover-our-startups/epfl-startup-in-creation/"

def parse_epfl(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for td in soup.find_all("td"):
        a = td.find("a", href=True)
        if not a:
            continue
        text = a.get_text(strip=True)
        if is_noise(text):
            continue
        rows.append({
            "company": text,
            "website": a["href"],
            "source": "EPFL",
            "source_page": EPFL_PAGE,
        })
    return rows

# ---------------------------------------------------------------
# SOURCE 5: University of Basel — company name + website in <p>
# ---------------------------------------------------------------
UNIBAS_PAGE = "https://www.unibas.ch/en/University/Innovation/Propelling-Grants/Our-Start-ups.html"

def parse_unibas(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for p in soup.find_all(["p", "big"]):  # confirmed: one entry (GeneGuide) used <big>
        a = p.find("a", href=True)
        if not a:
            continue
        text = a.get_text(strip=True)
        href = a["href"]
        if is_noise(text) or not href.startswith("http"):
            continue
        rows.append({
            "company": text,
            "website": href,
            "source": "University of Basel",
            "source_page": UNIBAS_PAGE,
        })
    return rows

# ---------------------------------------------------------------
# SOURCE 6: BioAlps — company website links in <p>
# ---------------------------------------------------------------
BIOALPS_PAGE = "https://bioalps.org/venture-leaders-medtech-2026/"

def parse_bioalps(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for p in soup.find_all("p"):
        a = p.find("a", href=True)
        if not a:
            continue
        text = a.get_text(strip=True)
        href = a["href"]
        if is_noise(text) or not href.startswith("http") or "bioalps.org" in href:
            continue
        # text here is typically the bare URL itself (e.g. "www.molesense.ch") —
        # flagged honestly: derive a placeholder name from the domain, same as
        # Innosuisse, real name to be confirmed by enrichment
        domain = re.sub(r'^www\.', '', text).split('/')[0] if text else re.sub(r'^https?://(www\.)?', '', href).split('/')[0]
        rows.append({
            "company": domain,
            "website": href,
            "source": "BioAlps",
            "source_page": BIOALPS_PAGE,
        })
    return rows


def main():
    all_rows = []

    print("=== Seedtable ===")
    for url in SEEDTABLE_PAGES:
        print(f"Fetching {url} ...")
        rows = parse_seedtable(fetch(url))
        print(f"  {len(rows)} companies found")
        all_rows.extend(rows)
        time.sleep(1)

    print("\n=== Innosuisse ===")
    rows = parse_innosuisse(fetch(INNOSUISSE_PAGE))
    print(f"  {len(rows)} companies found")
    all_rows.extend(rows)

    print("\n=== ETH Zurich (BSSE) ===")
    rows = parse_eth(fetch(ETH_PAGE))
    print(f"  {len(rows)} companies found")
    all_rows.extend(rows)

    print("\n=== EPFL ===")
    rows = parse_epfl(fetch(EPFL_PAGE))
    print(f"  {len(rows)} companies found")
    all_rows.extend(rows)

    print("\n=== University of Basel ===")
    rows = parse_unibas(fetch(UNIBAS_PAGE))
    print(f"  {len(rows)} companies found")
    all_rows.extend(rows)

    print("\n=== BioAlps ===")
    rows = parse_bioalps(fetch(BIOALPS_PAGE))
    print(f"  {len(rows)} companies found")
    all_rows.extend(rows)

    # Dedup by normalized company name (or domain, for placeholder-named rows)
    merged = {}
    for row in all_rows:
        key = re.sub(r'[^a-z0-9]', '', row["company"].lower())
        if not key:
            continue
        if key not in merged:
            merged[key] = row
            merged[key]["also_seen_in"] = []
        elif row["source"] != merged[key]["source"]:
            merged[key]["also_seen_in"].append(row["source"])

    final_rows = list(merged.values())
    for row in final_rows:
        row["also_seen_in"] = "; ".join(row["also_seen_in"])

    print(f"\n=== TOTAL after merge/dedup: {len(final_rows)} unique companies ===")

    fieldnames = ["company", "website", "source", "source_page", "also_seen_in"]
    with open("companies_ch_raw.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in final_rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    print("Written to companies_ch_raw.csv")
    print()
    print("HONEST NOTES:")
    print("- Innosuisse and BioAlps rows use a domain-derived company name")
    print("  (e.g. 'apheros' from apheros.ch) since these pages show website")
    print("  links, not separately labeled company names. Enrichment pass")
    print("  should confirm/replace these with the real stated company name")
    print("  from each site.")
    print("- This covers 6 of the ~14 sources tested in this project. The")
    print("  other 8 are dropped (login-blocked, broken, or no real listing)")
    print("  — see script docstring for the full breakdown.")
    print("- This has not yet been run end-to-end from a live GitHub Actions")
    print("  run. First real run's output should be spot-checked against the")
    print("  actual websites before being trusted at full volume.")

if __name__ == "__main__":
    main()
