#!/usr/bin/env python3
"""
SWITZERLAND ENRICHMENT — v2, rebuilt to match discover_ch.py's real
output columns (company, city, website, founder_name,
founder_contact_masked, source, source_page, also_seen_in).

What this does:
  For each company, if we already have a website, visit it directly and
  look for a real founder/CEO name and a real, working email or phone
  on the site itself (About, Team, Contact pages).

  For companies with no website yet (most of the PDF and Innosuisse-
  without-a-clean-url rows), this does NOT guess a domain — same rule
  as the advisors project's lesson: guessing domains creates a real risk
  of attributing the wrong company's contact info. Those rows are left
  marked "no website found" rather than guessed at.

Honest scope: this does not invent a name, email, or phone. Anything not
found on the company's own site is marked "NOT FOUND", never guessed.
"""
import csv
import re
import time
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (research; leadflow-ch-enrich/1.0)"}

EMAIL_RE = re.compile(r'[\w.\-]+@[\w\-]+\.[a-zA-Z]{2,}')
PHONE_RE = re.compile(r'(\+41|0)\s?\d{2}\s?\d{3}\s?\d{2}\s?\d{2}')
FOUNDER_KEYWORDS = ["founder", "co-founder", "ceo", "chief executive",
                     "gegründet von", "fondateur", "fondatrice"]
TEAM_PATHS = ["/about", "/team", "/about-us", "/contact", "/company",
              "/über-uns", "/a-propos"]

def fetch(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None

def normalize_website(url):
    if not url:
        return None
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    return url

def extract_founder_snippet(html):
    """Returns a short text window around the first founder/CEO mention —
    a lead for manual confirmation, not an asserted name on its own."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    lowered = text.lower()
    for kw in FOUNDER_KEYWORDS:
        idx = lowered.find(kw)
        if idx == -1:
            continue
        window = text[max(0, idx-60):idx+60]
        return window.strip()
    return None

def extract_contact(html):
    email = EMAIL_RE.search(html)
    phone = PHONE_RE.search(html)
    return (email.group(0) if email else None, phone.group(0) if phone else None)

def enrich_company(website):
    """Try the homepage first, then a few common team/about/contact paths."""
    if not website:
        return None, None, None

    pages_to_try = [website]
    base = website.rstrip("/")
    for path in TEAM_PATHS:
        pages_to_try.append(base + path)

    for url in pages_to_try:
        html = fetch(url)
        if not html:
            continue
        founder_snippet = extract_founder_snippet(html)
        email, phone = extract_contact(html)
        if founder_snippet or email or phone:
            return founder_snippet, email, phone

    return None, None, None

def main():
    rows = list(csv.DictReader(open("companies_ch_raw.csv")))
    print(f"Enriching {len(rows)} companies")

    out_rows = []
    no_website_count = 0
    found_count = 0

    for i, row in enumerate(rows):
        website = normalize_website(row.get("website", ""))

        # If discovery already found a founder name (e.g. from Innosuisse
        # or Seedtable), keep that — don't overwrite with a weaker result
        existing_founder = row.get("founder_name", "").strip()
        existing_contact = row.get("founder_contact_masked", "").strip()

        if not website:
            row["founder_snippet"] = "NOT FOUND — no website available to check"
            row["email"] = "NOT FOUND"
            row["phone"] = "NOT FOUND"
            no_website_count += 1
            out_rows.append(row)
            if i % 50 == 0:
                print(f"  [{i+1}/{len(rows)}] {row['company']}: no website, skipped")
            continue

        founder_snippet, email, phone = enrich_company(website)

        row["founder_snippet"] = founder_snippet or (
            f"Discovery found: {existing_founder}" if existing_founder else "NOT FOUND")
        row["email"] = email or (existing_contact if existing_contact else "NOT FOUND")
        row["phone"] = phone or "NOT FOUND"

        if founder_snippet or email or phone or existing_founder:
            found_count += 1

        out_rows.append(row)
        if i % 25 == 0:
            status = "found detail" if (founder_snippet or email or phone) else "none"
            print(f"  [{i+1}/{len(rows)}] {row['company']}: {status}")
        time.sleep(0.5)

    fieldnames = list(rows[0].keys()) + ["founder_snippet", "email", "phone"] if rows else []
    # dedupe fieldnames while preserving order (founder_name/founder_contact_masked
    # already exist from discovery, keep them alongside the new enrichment fields)
    seen = set()
    fieldnames = [f for f in fieldnames if not (f in seen or seen.add(f))]

    with open("companies_ch_enriched.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\nDone. {len(out_rows)} companies processed.")
    print(f"No website available: {no_website_count} ({no_website_count*100//max(1,len(out_rows))}%)")
    print(f"Some contact/founder detail found: {found_count} ({found_count*100//max(1,len(out_rows))}%)")
    print()
    print("HONEST NOTES:")
    print("- Rows with no website (mostly PDF and some Innosuisse entries) are")
    print("  marked NOT FOUND rather than guessed — same discipline as the")
    print("  advisors project: no domain-guessing, that created wrong-company")
    print("  risk before.")
    print("- founder_snippet is a short text window, a LEAD for manual")
    print("  confirmation, not an asserted fact — same as every enrichment")
    print("  pass in this project.")
    print("- This will be the slowest step yet since it visits multiple pages")
    print("  per company with a website. Expect this run to take longer than")
    print("  discovery did.")

if __name__ == "__main__":
    main()
