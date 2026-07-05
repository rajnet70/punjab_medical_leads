#!/usr/bin/env python3
"""
LeadFlow — ICP Enrichment + Signal Indicator
Second stage after icp_scraper.py discovery.

Takes each discovered consultancy, fetches its own website, and extracts a
public-only profile: founder, role, founding year, size, focus, published
contact, hunger signals, LinkedIn. Then assigns a single ICP SIGNAL tier:

  HOT      🔥  founder-led + startup-facing + hungry + boutique (Tobias/specculo-like)
  STRONG   ⭐  boutique + regulatory + founder-led, most signals present
  GOOD     ✅  fits profile, missing a signal or two
  QUALIFY  ⚪  regulatory but larger/established/ambiguous — glance manually
  LOW FIT  ❌  too big / enterprise / wrong profile — skip

Website-only. No personal-email guessing. Gaps marked 'not published'.
"""

import csv
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = Path("output")
IN_CSV = OUTPUT_DIR / "icp_consultancies.csv"
OUT_CSV = OUTPUT_DIR / "icp_enriched.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LeadFlowResearchBot/0.1)"}

# Pages likely to hold founder / about / contact info
ABOUT_HINTS = ["about", "team", "who-we-are", "our-story", "company", "people", "founder"]
CONTACT_HINTS = ["contact", "get-in-touch", "reach"]

FOUNDER_PATTERNS = [
    r"founded by ([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}),?\s+(?:the\s+)?(?:founder|co-founder|managing director|ceo|owner)",
    r"(?:founder|co-founder|managing director|ceo)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
    # "..., Kenneth recognised..." then "Specculo was founded" — name near 'founded'
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+(?:recognised|recognized|realised|realized|saw|decided|started|established|launched|created)",
    # "Kenneth brings over a decade" — name + 'brings/has X years'
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,1})\s+(?:brings|has)\s+(?:over\s+)?(?:a\s+)?(?:decade|\d+\s+years)",
    # "Mike is the Founder and CEO" — name + is + (the) + founder/role
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,1})\s+is\s+(?:the\s+|a\s+)?(?:founder|co-founder|managing director|ceo|owner|principal)",
]

# Words that are NOT names (avoid false positives)
NAME_STOPWORDS = {"the", "our", "we", "us", "this", "with", "after", "today", "what",
                  "specculo", "based", "join", "get", "about", "who", "from", "years",
                  "medical", "regulatory", "quality", "founded", "prior", "before"}
ROLE_PATTERN = r"(Founder(?:\s*&\s*CEO)?|Co-Founder|Managing Director|Principal Consultant|CEO|Owner)"
YEAR_PATTERN = r"(?:founded|established|since|est\.?)\s*(?:in\s*)?(19[89]\d|20[0-2]\d)"
EMAIL_PATTERN = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

# Signal keyword banks
STARTUP = ["start-up", "startup", "start up", "sme", "smes", "small and medium",
           "small to medium", "aspiring", "cost-effective", "early-stage", "early stage"]
BOUTIQUE = ["specialist", "specialized", "specialised", "boutique", "personalized",
            "personalised", "tailored", "hands-on", "hands on", "independent",
            "small firm", "small team", "one-man", "founded"]
HUNGRY = ["newsletter", "get in touch", "free consult", "book a call", "contact us",
          "subscribe", "let's talk", "schedule a", "reach out", "webinar", "speaking"]
REG = ["regulatory", "mdr", "ivdr", "iso 13485", "quality assurance", "regulatory affairs",
       "qms", "ce mark", "quality management"]
LARGE = ["worldwide", "global offices", "multinational", "125 years", "90 employees",
         "employees working", "leading consultancy companies", "over 20 years", "large scale",
         "25+ locations", "global organizations", "global organisations"]


def fetch(url: str, timeout=20) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception:
        return ""


def find_subpages(base_url: str, html: str) -> list[str]:
    """Find About/Team/Contact sub-pages to enrich from."""
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if any(h in href for h in ABOUT_HINTS + CONTACT_HINTS):
            full = href if href.startswith("http") else base_url.rstrip("/") + "/" + href.lstrip("/")
            if base_url.split("//")[-1].split("/")[0] in full:  # same domain
                found.append(full)
    # de-dupe, cap at 3 to stay polite/fast
    seen, out = set(), []
    for u in found:
        if u not in seen:
            seen.add(u); out.append(u)
    return out[:3]


def extract_profile(text: str, html: str) -> dict:
    prof = {"founder": "", "role": "", "founded": "", "email": "", "linkedin": ""}

    for pat in FOUNDER_PATTERNS:
        m = re.search(pat, text)
        if m:
            cand = m.group(1).strip()
            first_word = cand.split()[0].lower() if cand else ""
            if first_word not in NAME_STOPWORDS and len(cand) > 2:
                prof["founder"] = cand
                break

    m = re.search(ROLE_PATTERN, text, re.I)
    if m: prof["role"] = m.group(1)

    m = re.search(YEAR_PATTERN, text, re.I)
    if m: prof["founded"] = m.group(1)

    # published email (prefer info@/contact@ over personal)
    emails = re.findall(EMAIL_PATTERN, html)
    emails = [e for e in emails if not e.endswith((".png", ".jpg", ".gif", ".svg"))]
    if emails:
        generic = [e for e in emails if e.split("@")[0].lower() in
                   ("info", "contact", "hello", "office", "admin", "enquiries", "mail")]
        prof["email"] = generic[0] if generic else emails[0]

    m = re.search(r"(https?://[a-z]{2,3}\.linkedin\.com/company/[a-zA-Z0-9\-_]+)", html)
    if m: prof["linkedin"] = m.group(1)

    return prof


def compute_signal(desc: str, prof: dict, full_text: str) -> tuple[str, str]:
    """Return (signal_tier, why_note)."""
    t = (desc + " " + full_text).lower()

    startup = any(s in t for s in STARTUP)
    boutique = any(s in t for s in BOUTIQUE)
    hungry = any(s in t for s in HUNGRY)
    reg = any(s in t for s in REG)
    large = any(s in t for s in LARGE)
    founder_led = bool(prof.get("founder")) or "founded by" in t or "one-man" in t

    # scoring
    score = 0
    reasons = []
    if founder_led: score += 2; reasons.append("founder-led")
    if startup:     score += 2; reasons.append("startup/SME-facing")
    if boutique:    score += 1; reasons.append("boutique/specialist")
    if hungry:      score += 1; reasons.append("actively marketing")
    if reg:         score += 1; reasons.append("regulatory/QA focus")
    if large:       score -= 3; reasons.append("larger/global firm")

    if large and score < 2:
        tier = "❌ LOW FIT"
    elif score >= 6:
        tier = "🔥 HOT"
    elif score >= 4:
        tier = "⭐ STRONG"
    elif score >= 2:
        tier = "✅ GOOD"
    else:
        tier = "⚪ QUALIFY"

    why = ", ".join(reasons) if reasons else "limited public signal"
    return tier, why


def enrich_one(row: dict) -> dict:
    base = row["website"]
    if not base.startswith("http"):
        base = "https://" + base

    home = fetch(base)
    combined_text = ""
    combined_html = ""
    if home:
        combined_html += home
        combined_text += BeautifulSoup(home, "html.parser").get_text(" ", strip=True)
        for sub in find_subpages(base, home):
            sub_html = fetch(sub)
            if sub_html:
                combined_html += " " + sub_html
                combined_text += " " + BeautifulSoup(sub_html, "html.parser").get_text(" ", strip=True)
            time.sleep(1)

    prof = extract_profile(combined_text, combined_html) if combined_text else empty_profile()

    tier, why = compute_signal(row.get("description", ""), prof, combined_text)

    row["signal"] = tier
    row["signal_reason"] = why
    row["founder"] = prof["founder"] or "not published"
    row["role"] = prof["role"] or ""
    row["founded_year"] = prof["founded"] or ""
    row["public_email"] = prof["email"] or "not published"
    row["linkedin"] = prof["linkedin"] or ""
    row["enriched"] = "yes" if combined_text else "site unreachable"
    return row


def empty_profile():
    return {"founder": "", "role": "", "founded": "", "email": "", "linkedin": ""}


def main():
    if not IN_CSV.exists():
        print(f"! {IN_CSV} not found — run icp_scraper.py first.")
        return
    with open(IN_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"Enriching {len(rows)} consultancies (website-only)...\n")
    enriched = []
    for i, row in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {row['company']} ...", end=" ")
        try:
            r = enrich_one(row)
            print(r["signal"])
            enriched.append(r)
        except Exception as e:
            print(f"error: {e}")
            row["signal"] = "⚪ QUALIFY"; row["signal_reason"] = "enrichment error"
            enriched.append(row)
        time.sleep(1)

    # sort by signal tier
    tier_order = {"🔥 HOT": 0, "⭐ STRONG": 1, "✅ GOOD": 2, "⚪ QUALIFY": 3, "❌ LOW FIT": 4}
    enriched.sort(key=lambda r: tier_order.get(r.get("signal", "⚪ QUALIFY"), 3))

    fields = ["company", "country", "signal", "signal_reason", "founder", "role",
              "founded_year", "public_email", "linkedin", "icp_signals",
              "description", "website", "enriched", "source"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(enriched)

    from collections import Counter
    print(f"\n=== Enriched {len(enriched)} → {OUT_CSV} ===")
    print("By signal:", dict(Counter(r.get("signal") for r in enriched)))
    print("\nPriority (HOT / STRONG):")
    for r in enriched:
        if r.get("signal") in ("🔥 HOT", "⭐ STRONG"):
            print(f"  {r['signal']}  {r['company']} ({r['country']}) — {r['signal_reason']}"
                  f" | founder: {r['founder']}")


if __name__ == "__main__":
    main()
