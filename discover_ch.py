#!/usr/bin/env python3
"""
SWITZERLAND DISCOVERY — v3, rebuilt against REAL live page content (not
stale test snapshots). This fixes two silent failures from the previous
run and adds the PDF source that was tested successfully but never wired
into the actual collection script.

Sources in this version:
  1. Seedtable      — REBUILT. The site's layout changed since first
                       tested; now pulls structured company cards (name,
                       funding, industry, location, founder names +
                       partially-masked emails showing the domain).
  2. Innosuisse       — REBUILT. Real structure is a plain bullet list:
                       "Company Name: https://website.ch" grouped by year.
  3. ETH Zurich (BSSE) — unchanged, confirmed working pattern
  4. EPFL             — unchanged, confirmed working pattern
  5. University of Basel — unchanged, confirmed working pattern
  6. BioAlps          — unchanged, confirmed working pattern
  7. Swiss Medtech Day PDF — NEWLY WIRED IN. Confirmed working in testing
                       (853 companies, one per line) but was never added
                       to this script until now.

Still excluded (confirmed not usable): startup.ch, Swiss Biotech
Association, startupticker.ch (all login-blocked), medicalstartups.org
(415 error, unresolved), EU-Startups (no real listing on tested page).
"""
import csv
import re
import time
import io
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (research; leadflow-ch/1.0)"}

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
    "terms", "legal", "jobs", "career", "linkedin", "twitter",
    "facebook", "instagram", "youtube", "subscribe", "newsletter",
    "partners", "portfolio", "members", "membership", "financing",
    "coaching", "incubator", "technopark", "university", "networks",
    "industrial network", "economic promotion", "international markets",
    "innovation networks", "technology transfer", "farewell", "welcome",
    "wins its legal battle",
]

def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            return r
        print(f"  non-200 ({r.status_code}) for {url}")
    except Exception as e:
        print(f"  fetch error {url}: {e}")
    return None

def is_noise(text):
    if not text or len(text) < 2 or len(text) > 80:
        return True
    return any(w in text.lower() for w in SKIP_WORDS)

# ---------------------------------------------------------------
# SOURCE 1: Seedtable — REBUILT against real current page structure.
# Company cards follow: ### [Name](url) ... Industries: ... Location: ...
# Key people: - [Name](url) email_or_linkedin
# Parsed here from the markdown-rendered text structure directly.
# ---------------------------------------------------------------
SEEDTABLE_PAGES = [
    "https://www.seedtable.com/best-startups-in-switzerland",
    "https://www.seedtable.com/best-health-tech-startups-in-switzerland",
]

def parse_seedtable(resp):
    if not resp:
        return []
    text = resp.text
    rows = []
    # Company blocks start with "### [Name](url)" markdown-style heading link
    # (confirmed live: e.g. "### [Yokoy](https://www.seedtable.com/startups/...)")
    blocks = re.split(r'\n### \[', text)
    for block in blocks[1:]:
        name_match = re.match(r'([^\]]+)\]\(([^)]+)\)', block)
        if not name_match:
            continue
        name, profile_url = name_match.group(1).strip(), name_match.group(2).strip()
        if is_noise(name):
            continue
        # Location line: "#### Location:\n\n[City](...) [Country](...)"
        loc_match = re.search(r'#### Location:\s*\n+\[([^\]]+)\]', block)
        city = loc_match.group(1).strip() if loc_match else ""
        # Key people line(s): "- [Name](url) **email pattern**" or "[linkedin]"
        people = re.findall(r'-\s*\[([^\]]+)\]\([^)]+\)\s*([^\n]*)', block)
        founder_name, founder_contact = "", ""
        if people:
            founder_name = people[0][0].strip()
            contact_raw = people[0][1].strip()
            founder_contact = contact_raw if contact_raw else ""
        rows.append({
            "company": name,
            "city": city,
            "website": "",  # not directly shown; profile_url is Seedtable's own page
            "founder_name": founder_name,
            "founder_contact_masked": founder_contact,
            "source": "Seedtable",
            "source_page": profile_url,
        })
    return rows

# ---------------------------------------------------------------
# SOURCE 2: Innosuisse — REBUILT. Real structure: "Name: https://url"
# in a plain bullet list, grouped under year headings.
# ---------------------------------------------------------------
INNOSUISSE_PAGE = "https://www.innosuisse.admin.ch/en/approved-start-up-innovation-projects"

def parse_innosuisse(resp):
    if not resp:
        return []
    text = resp.text
    rows = []
    # Pattern confirmed live: "- CompanyName AG: <https://website.ch>" or
    # "- CompanyName AG: [https://website.ch](https://website.ch/)"
    for m in re.finditer(r'-\s*([A-Z][\w&().,\'\-\s]+?):\s*(?:<(https?://[^>]+)>|\[(https?://[^\]]+)\]\(([^)]+)\))', text):
        name = m.group(1).strip()
        website = m.group(2) or m.group(3) or m.group(4) or ""
        if is_noise(name):
            continue
        rows.append({
            "company": name,
            "city": "",
            "website": website,
            "founder_name": "",
            "founder_contact_masked": "",
            "source": "Innosuisse",
            "source_page": INNOSUISSE_PAGE,
        })
    return rows

# ---------------------------------------------------------------
# SOURCE 3: ETH Zurich (BSSE) — unchanged, confirmed pattern
# ---------------------------------------------------------------
ETH_PAGE = "https://bsse.ethz.ch/department/spin-offs.html"

def parse_eth(resp):
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    for p in soup.find_all("p"):
        a = p.find("a", href=True)
        if not a:
            continue
        text = a.get_text(strip=True)
        if text.lower().startswith("external page"):
            text = text[len("external page"):].strip()
        if is_noise(text):
            continue
        rows.append({
            "company": text, "city": "", "website": a["href"],
            "founder_name": "", "founder_contact_masked": "",
            "source": "ETH Zurich (BSSE)", "source_page": ETH_PAGE,
        })
    return rows

# ---------------------------------------------------------------
# SOURCE 4: EPFL — unchanged, confirmed pattern
# ---------------------------------------------------------------
EPFL_PAGE = "https://www.epfl.ch/innovation/startup/discover-our-startups/epfl-startup-in-creation/"

def parse_epfl(resp):
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    for td in soup.find_all("td"):
        a = td.find("a", href=True)
        if not a:
            continue
        text = a.get_text(strip=True)
        if is_noise(text):
            continue
        rows.append({
            "company": text, "city": "", "website": a["href"],
            "founder_name": "", "founder_contact_masked": "",
            "source": "EPFL", "source_page": EPFL_PAGE,
        })
    return rows

# ---------------------------------------------------------------
# SOURCE 5: University of Basel — unchanged, confirmed pattern
# ---------------------------------------------------------------
UNIBAS_PAGE = "https://www.unibas.ch/en/University/Innovation/Propelling-Grants/Our-Start-ups.html"

def parse_unibas(resp):
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    for p in soup.find_all(["p", "big"]):
        a = p.find("a", href=True)
        if not a:
            continue
        text = a.get_text(strip=True)
        href = a["href"]
        if is_noise(text) or not href.startswith("http"):
            continue
        rows.append({
            "company": text, "city": "", "website": href,
            "founder_name": "", "founder_contact_masked": "",
            "source": "University of Basel", "source_page": UNIBAS_PAGE,
        })
    return rows

# ---------------------------------------------------------------
# SOURCE 6: BioAlps — unchanged, confirmed pattern
# ---------------------------------------------------------------
BIOALPS_PAGE = "https://bioalps.org/venture-leaders-medtech-2026/"

def parse_bioalps(resp):
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    for p in soup.find_all("p"):
        a = p.find("a", href=True)
        if not a:
            continue
        text = a.get_text(strip=True)
        href = a["href"]
        if is_noise(text) or not href.startswith("http") or "bioalps.org" in href:
            continue
        domain = re.sub(r'^www\.', '', text).split('/')[0] if text else re.sub(r'^https?://(www\.)?', '', href).split('/')[0]
        rows.append({
            "company": domain, "city": "", "website": href,
            "founder_name": "", "founder_contact_masked": "",
            "source": "BioAlps", "source_page": BIOALPS_PAGE,
        })
    return rows

# ---------------------------------------------------------------
# SOURCE 7: Swiss Medtech Day PDF — NEWLY WIRED IN
# Confirmed pattern: plain text, "Company Name  N" (name + participant
# count) one per line, across 9 pages.
# ---------------------------------------------------------------
SMD_PDF_URL = "https://www.swiss-medtech.ch/sites/default/files/2026-06/SMD26_Companies_260610.pdf"

def parse_swiss_medtech_pdf():
    try:
        import pdfplumber
    except ImportError:
        print("  pdfplumber not installed — skipping PDF source")
        return []
    r = fetch(SMD_PDF_URL)
    if not r:
        return []
    rows = []
    try:
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.split("\n"):
                    # Confirmed pattern: "Company Name AG 2" — name followed
                    # by a trailing participant count digit(s)
                    m = re.match(r'^([A-Za-z][\w&().,\'\-\s]+?)\s+(\d+)$', line.strip())
                    if not m:
                        continue
                    name = m.group(1).strip()
                    if is_noise(name) or name.lower() in (
                        "organisation", "swiss medtech day 2026 company list"):
                        continue
                    rows.append({
                        "company": name, "city": "", "website": "",
                        "founder_name": "", "founder_contact_masked": "",
                        "source": "Swiss Medtech Day 2026",
                        "source_page": SMD_PDF_URL,
                    })
    except Exception as e:
        print(f"  PDF parse error: {e}")
    return rows


def main():
    all_rows = []

    print("=== Seedtable (rebuilt) ===")
    for url in SEEDTABLE_PAGES:
        print(f"Fetching {url} ...")
        rows = parse_seedtable(fetch(url))
        print(f"  {len(rows)} companies found")
        all_rows.extend(rows)
        time.sleep(1)

    print("\n=== Innosuisse (rebuilt) ===")
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

    print("\n=== Swiss Medtech Day 2026 PDF ===")
    rows = parse_swiss_medtech_pdf()
    print(f"  {len(rows)} companies found")
    all_rows.extend(rows)

    # Dedup by normalized company name
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

    fieldnames = ["company", "city", "website", "founder_name",
                  "founder_contact_masked", "source", "source_page", "also_seen_in"]
    with open("companies_ch_raw.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in final_rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    print("Written to companies_ch_raw.csv")
    print()
    print("HONEST NOTES:")
    print("- Seedtable and Innosuisse parsers were REBUILT against real live")
    print("  page content fetched directly during this fix, not the earlier")
    print("  test snapshots — those pages had changed or were misread before.")
    print("- The PDF source is newly wired in; previously it was tested")
    print("  successfully but never actually added to this collection script.")
    print("- founder_contact_masked from Seedtable shows a partially masked")
    print("  email revealing the domain (e.g. '***.***@nexthink.com') — full")
    print("  email needs separate enrichment, this is a lead not a complete one.")
    print("- Still not run end-to-end from live GitHub Actions with these")
    print("  fixes — spot-check the first real output before trusting volume.")

if __name__ == "__main__":
    main()
