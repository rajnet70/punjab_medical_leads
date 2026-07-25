#!/usr/bin/env python3
"""
SWITZERLAND ENRICHMENT — v3.

For each company:
  1. If it already has a website (from discovery), enrich it directly —
     visit the site, look for founder/CEO name, email, phone.
  2. If it has NO website (mostly the 460 PDF-only names), first do a
     careful, real web search using the exact company name — only accept
     a result if the company name clearly appears in that result's own
     title. If confident, use that as the website and continue to step 1.
     If no confident match, mark as "NOT FOUND" — never guessed.

This folds the separate "find websites" step directly into enrichment,
since both jobs are really the same thing: visiting a company's real
online presence to pull out real detail. No domain is ever guessed from
a company name.
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

def normalize(name):
    name = name.lower()
    name = re.sub(r'\b(ag|sa|gmbh|sàrl|sarl|ltd|llc|inc)\b\.?', '', name)
    name = re.sub(r'[^a-z0-9]', '', name)
    return name

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

def find_website_by_search(company_name):
    """
    Real, careful search using the company's exact name — via Bing, which
    (unlike some search engines) reliably serves plain HTTP requests
    without needing an account or API key. Only returns a result if the
    company name genuinely appears in that result's own title — otherwise
    returns None. Never constructs or guesses a domain from the name.
    """
    try:
        r = requests.get(
            "https://www.bing.com/search",
            params={"q": f'"{company_name}" Switzerland official website'},
            headers=HEADERS, timeout=15
        )
        if r.status_code != 200:
            return None
    except Exception:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    name_key = normalize(company_name)
    if not name_key:
        return None

    for result in soup.select("li.b_algo"):
        title_el = result.find("h2")
        link_el = result.find("a", href=True)
        if not title_el or not link_el:
            continue
        title_text = title_el.get_text(strip=True)
        title_key = normalize(title_text)
        href = link_el["href"]
        # only accept a confident match: company name genuinely in the title,
        # and it's not a directory/listing site rather than the real company
        if name_key in title_key and not any(
            junk in href for junk in ["linkedin.com", "bloomberg.com",
                                        "crunchbase.com", "zefix", "moneyhouse"]):
            return href
    return None

def extract_founder_snippet(html):
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
    website_found_by_search = 0
    no_website_count = 0
    found_count = 0

    for i, row in enumerate(rows):
        website = normalize_website(row.get("website", ""))
        existing_founder = row.get("founder_name", "").strip()
        existing_contact = row.get("founder_contact_masked", "").strip()

        # Step 1: if no website, try to find one via a careful, confident search
        if not website:
            found_site = find_website_by_search(row["company"])
            if found_site:
                website = found_site
                row["website"] = found_site
                row["website_source"] = "found via search, name-confirmed"
                website_found_by_search += 1
            time.sleep(1)  # polite delay for the search itself

        if not website:
            row["founder_snippet"] = "NOT FOUND — no website available or found"
            row["email"] = "NOT FOUND"
            row["phone"] = "NOT FOUND"
            no_website_count += 1
            out_rows.append(row)
            if i % 50 == 0:
                print(f"  [{i+1}/{len(rows)}] {row['company']}: no website, skipped")
            continue

        # Step 2: enrich using the website (existing or just found)
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

    fieldnames = list(rows[0].keys())
    for extra in ["website_source", "founder_snippet", "email", "phone"]:
        if extra not in fieldnames:
            fieldnames.append(extra)

    with open("companies_ch_enriched.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in out_rows:
            for field in fieldnames:
                row.setdefault(field, "")
            writer.writerow(row)

    print(f"\nDone. {len(out_rows)} companies processed.")
    print(f"Websites found via search (had none from discovery): {website_found_by_search}")
    print(f"Still no website at all: {no_website_count} ({no_website_count*100//max(1,len(out_rows))}%)")
    print(f"Some contact/founder detail found: {found_count} ({found_count*100//max(1,len(out_rows))}%)")
    print()
    print("HONEST NOTES:")
    print("- No domain was ever guessed or constructed from a company name.")
    print("- A found website is only accepted if the company's exact name")
    print("  appears in the search result's own title — uncertain matches are")
    print("  left NOT FOUND rather than risking the wrong company's contact info.")
    print("- This run will be noticeably slower than before since it now also")
    print("  searches for missing websites, not just enriches existing ones.")
    print("- website_source column shows exactly how each website was obtained,")
    print("  for spot-checking before this goes anywhere near a client.")

if __name__ == "__main__":
    main()
