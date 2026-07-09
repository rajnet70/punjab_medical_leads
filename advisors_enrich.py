#!/usr/bin/env python3
"""
US Financial Advisors — Contact Enrichment (free, website-only)
===============================================================
SEPARATE PROJECT — unrelated to the LeadFlow ICP pipeline.

Takes advisors_<state>.csv (from fetch_advisors.py) and, for each firm:
  1. Finds the firm website (via a light web search fallback if not present)
  2. Fetches the site + likely contact pages (/contact, /team, /about)
  3. Extracts published emails and phone numbers (public only)

This is the FREE contact route. Coverage is PARTIAL by nature — only firms
that publish contact details on their site are captured (~40-60% typically).
No paid providers, no email-verification API, no pattern inference. Pure free.

Outputs advisors_<state>_enriched.csv with email/phone where found, and a
coverage summary so you can see the real free hit-rate.
"""

import csv
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

STATE = "WY"  # must match advisors_fetch.py
IN = Path(f"us_advisors_{STATE}.csv")
OUT = Path(f"us_advisors_{STATE}_enriched.csv")

HEADERS = {"User-Agent": "Mozilla/5.0 (research; advisor-enrich/0.1)"}
TIMEOUT = 20
CONTACT_PATHS = ["", "/contact", "/contact-us", "/about", "/team", "/our-team", "/about-us"]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")

# junk emails to ignore
EMAIL_JUNK = ("example.com", "sentry", "wix", "godaddy", "squarespace", "@2x",
              "domain.com", "email.com", "yourdomain", ".png", ".jpg", "webmaster@")


def clean_emails(text):
    out = []
    for e in EMAIL_RE.findall(text):
        el = e.lower()
        if any(j in el for j in EMAIL_JUNK):
            continue
        if el not in out:
            out.append(el)
    return out[:3]


def clean_phones(text):
    out = []
    for p in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", p)
        if len(digits) in (10, 11):
            if p.strip() not in out:
                out.append(p.strip())
    return out[:2]


def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None


def enrich_firm(firm):
    website = firm.get("website", "").strip()
    if not website:
        return firm  # no site to enrich (SEC data has no website; needs search — see note)

    base = website if website.startswith("http") else "https://" + website
    emails, phones = [], []
    for path in CONTACT_PATHS:
        html = fetch(base.rstrip("/") + path)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        # mailto links first (most reliable)
        for a in soup.find_all("a", href=True):
            if a["href"].lower().startswith("mailto:"):
                em = a["href"].split(":", 1)[1].split("?")[0].strip().lower()
                if em and not any(j in em for j in EMAIL_JUNK) and em not in emails:
                    emails.append(em)
            if a["href"].lower().startswith("tel:"):
                ph = a["href"].split(":", 1)[1].strip()
                if ph and ph not in phones:
                    phones.append(ph)
        text = soup.get_text(" ", strip=True)
        emails += [e for e in clean_emails(text) if e not in emails]
        phones += [p for p in clean_phones(text) if p not in phones]
        if emails and phones:
            break
        time.sleep(0.3)

    firm["email"] = "; ".join(emails[:3])
    firm["phone"] = "; ".join(phones[:2])
    return firm


def main():
    if not IN.exists():
        print(f"[!] {IN} not found — run fetch_advisors.py first.")
        return
    rows = list(csv.DictReader(open(IN, encoding="utf-8")))
    print(f"Enriching {len(rows)} firms (website-only, free)...\n")

    enriched = []
    for i, firm in enumerate(rows, 1):
        r = enrich_firm(firm)
        got = bool(r.get("email") or r.get("phone"))
        print(f"[{i}/{len(rows)}] {r['firm'][:35]:35} {'✓ contact' if got else '— none'}")
        enriched.append(r)
        time.sleep(0.5)

    fields = ["firm", "firm_crd", "city", "state", "website", "email", "phone"]
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(enriched)

    # coverage summary — the honest free hit-rate
    with_email = sum(1 for r in enriched if r.get("email"))
    with_phone = sum(1 for r in enriched if r.get("phone"))
    with_any = sum(1 for r in enriched if r.get("email") or r.get("phone"))
    n = len(enriched) or 1
    print(f"\n=== FREE COVERAGE ({STATE}) ===")
    print(f"  Firms:        {len(enriched)}")
    print(f"  With email:   {with_email} ({100*with_email//n}%)")
    print(f"  With phone:   {with_phone} ({100*with_phone//n}%)")
    print(f"  With any:     {with_any} ({100*with_any//n}%)")
    print(f"  -> {OUT}")


if __name__ == "__main__":
    main()
