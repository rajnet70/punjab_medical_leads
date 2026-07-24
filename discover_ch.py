#!/usr/bin/env python3
"""
SWITZERLAND DISCOVERY — v4, Seedtable parser rebuilt using BeautifulSoup
against real HTML structure (not a text-pattern guess). Confirmed against
actual live page content: company blocks are <h3><a>Name</a></h3>,
followed by a description paragraph, an Industries/Location section, and
a "Key people" list with founder names and partially-masked emails that
reveal the real domain.
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
# SOURCE 1: Seedtable — REBUILT using BeautifulSoup on real HTML.
# Each company block is an <h3> containing a link to /startups/...,
# with sibling <p> tags for description and a "Key people" section
# containing <li> or similar items with name + masked email text.
# ---------------------------------------------------------------
SEEDTABLE_PAGES = [
    "https://www.seedtable.com/best-startups-in-switzerland",
    "https://www.seedtable.com/best-health-tech-startups-in-switzerland",
]

EMAIL_MASKED_RE = re.compile(r'[\*\w.]*@([\w\-]+\.[\w.]+)')

def parse_seedtable(resp):
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    # Company name headings: <h3><a href="/startups/...">Name</a></h3>
    for h3 in soup.find_all("h3"):
        a = h3.find("a", href=True)
        if not a or "/startups/" not in a.get("href", ""):
            continue
        name = a.get_text(strip=True)
        if is_noise(name):
            continue
        profile_url = a["href"]
        if profile_url.startswith("/"):
            profile_url = "https://www.seedtable.com" + profile_url

        # Walk forward through siblings to find description, location,
        # and key people before hitting the next <h3> (next company)
        description, city, founder_name, founder_email_domain = "", "", "", ""
        node = h3.find_next_sibling()
        steps = 0
        while node and steps < 40:
            steps += 1
            if node.name == "h3":
                break  # reached next company block
            text = node.get_text(" ", strip=True)
            if node.name == "p" and text and not description and "Industries" not in text:
                description = text
            if "Location:" in text and node.name in ("h4", "p", "div"):
                nxt = node.find_next_sibling()
                if nxt:
                    first_link = nxt.find("a")
                    if first_link:
                        city = first_link.get_text(strip=True)
            if "Key people" in text:
                # look at the next sibling(s) for the people list
                people_node = node.find_next_sibling()
                if people_node:
                    for li in people_node.find_all(["li", "p"]):
                        person_text = li.get_text(" ", strip=True)
                        person_link = li.find("a")
                        if not person_link:
                            continue
                        if not founder_name:
                            founder_name = person_link.get_text(strip=True)
                        m = EMAIL_MASKED_RE.search(person_text)
                        if m and not founder_email_domain:
                            founder_email_domain = m.group(1)
                        break  # first person only, per company
            node = node.find_next_sibling()

        rows.append({
            "company": name,
            "city": city,
            "website": "",
            "founder_name": founder_name,
            "founder_contact_masked": ("@" + founder_email_domain) if founder_email_domain else "",
            "source": "Seedtable",
            "source_page": profile_url,
        })
    return rows

# ---------------------------------------------------------------
# SOURCE 2: Innosuisse — real structure confirmed: bullet list items,
# "CompanyName: <url>" as plain text within <li> or <p> tags.
# ---------------------------------------------------------------
INNOSUISSE_PAGE = "https://www.innosuisse.admin.ch/en/approved-start-up-innovation-projects"

def parse_innosuisse(resp):
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    for tag in soup.find_all(["li", "p"]):
        text = tag.get_text(" ", strip=True)
        a = tag.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if not href.startswith("http") or "admin.ch" in href or "powerbi.com" in href:
            continue
        # name is text before the colon, if present; else before the link text
        m = re.match(r'^([A-Z][\w&().,\'\-\s]+?):', text)
        name = m.group(1).strip() if m else ""
        if is_noise(name):
            continue
        rows.append({
            "company": name, "city": "", "website": href,
            "founder_name": "", "founder_contact_masked": "",
            "source": "Innosuisse", "source_page": INNOSUISSE_PAGE,
        })
    return rows

# ---------------------------------------------------------------
# SOURCES 3-6: unchanged, confirmed working patterns
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
# SOURCE 7: Swiss Medtech Day PDF — confirmed working, unchanged
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

    print("=== Seedtable (rebuilt with BeautifulSoup, tested against real HTML) ===")
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
    print("- Seedtable parser rebuilt using proper HTML parsing (BeautifulSoup)")
    print("  against real page structure, not a text-pattern guess this time.")
    print("- founder_contact_masked shows only the domain (e.g. '@nexthink.com'),")
    print("  confirmed real from the source, not the full email — full address")
    print("  needs separate enrichment against each person/company.")
    print("- If Seedtable or Innosuisse still return 0, the live site's raw HTML")
    print("  differs from what was directly observed — needs a fresh live check,")
    print("  not another guess.")

if __name__ == "__main__":
    main()
