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
                  "medical", "regulatory", "quality", "founded", "prior", "before",
                  "having", "being", "when", "since", "over", "more", "team", "company",
                  "firm", "consultancy", "consulting", "group", "services", "solutions",
                  "it", "his", "her", "their", "they", "she", "he", "was", "were", "are"}
ROLE_PATTERN = r"(Founder(?:\s*&\s*CEO)?|Co-Founder|Managing Director|Principal Consultant|CEO|Owner)"
YEAR_PATTERN = r"(?:founded|established|since|est\.?)\s*(?:in\s*)?(19[89]\d|20[0-2]\d)"
EMAIL_PATTERN = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

# Signal keyword banks
STARTUP = ["start-up", "startup", "start up", "sme", "smes", "small and medium",
           "small to medium", "aspiring", "cost-effective", "early-stage", "early stage"]
BOUTIQUE = ["specialist", "specialized", "specialised", "boutique", "personalized",
            "personalised", "tailored", "hands-on", "hands on", "independent",
            "small firm", "small team", "one-man", "founded"]
REG = ["regulatory", "mdr", "ivdr", "iso 13485", "quality assurance", "regulatory affairs",
       "qms", "ce mark", "quality management"]
LARGE = ["worldwide", "global offices", "multinational", "125 years", "90 employees",
         "employees working", "leading consultancy companies", "over 20 years", "large scale",
         "25+ locations", "global organizations", "global organisations", "more than 30 permanent"]

# --- SPEND / GROWTH-INTENT SIGNALS (the core buying trigger: firms investing to grow) ---
# Strongest: provable money/effort spent on business development.
SPEND_EXHIBIT = ["exhibit", "visit us at", "booth", "trade fair", "trade show",
                 "raps convergence", "medtech summit", "see us at", "meet us at",
                 "join us at", "sponsoring", " medica ", "compamed", "at medica"]
SPEND_MARKETING = ["newsletter", "subscribe", "webinar", "download our", "free guide",
                   "whitepaper", "white paper", "case study", "case studies", "blog",
                   "latest insights", "our insights"]
SPEND_HIRING = ["careers", "we're hiring", "we are hiring", "join our team", "job openings",
                "vacancies", "open positions", "now hiring"]
SPEND_GROWTH = ["expanding", "growing", "new service", "now offering", "recently launched",
                "book a call", "book a free", "free consultation", "get in touch",
                "schedule a", "let's talk", "contact us today"]
# The single strongest signal: hiring for business development / sales / marketing
SPEND_BD_HIRE = ["business development manager", "sales manager", "marketing manager",
                 "bd manager", "head of growth", "head of sales", "business development role"]


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


NON_NAME_WORDS = {"supplies","hospital","process","validation","device","medical","consulting",
                  "consultancy","group","firm","company","the","our","solutions","services",
                  "design","quality","regulatory","having","being","team","working","provides",
                  "offers","project","management","development","engineering","clinical",
                  "compliance","strategy","support","expert","experts","industry"}

def looks_like_person(cand: str) -> bool:
    """Conservative check that a candidate string is a real person name, not a company/common word."""
    words = cand.split()
    if not words:
        return False
    if len(words) > 3:
        return False
    # any business/common word disqualifies it
    if any(w.lower().strip(".,") in NON_NAME_WORDS for w in words):
        return False
    # must all be capitalized (name-like)
    if not all(w[0].isupper() for w in words if w):
        return False
    # single-word names are risky (often false matches) — require >=3 chars and not common
    if len(words) == 1 and len(words[0]) < 3:
        return False
    return True


def extract_profile(text: str, html: str, company_name: str = "") -> dict:
    prof = {"founder": "", "role": "", "founded": "", "email": "", "linkedin": ""}

    # Build a set of company-name words to exclude from founder matches
    company_words = set()
    if company_name:
        company_words = {w.lower().strip(".,") for w in company_name.split() if len(w) > 2}

    for pat in FOUNDER_PATTERNS:
        for m in re.finditer(pat, text):
            cand = m.group(1).strip()
            words = cand.split()
            first_word = words[0].lower() if words else ""
            cand_words = {w.lower().strip(".,") for w in words}
            # Reject if: stopword, or overlaps the company name, or looks like a single common word
            if first_word in NAME_STOPWORDS:
                continue
            if cand_words & company_words:            # candidate contains company name
                continue
            if len(cand) <= 2:
                continue
            if not looks_like_person(cand):        # strict person-name validation
                continue
            prof["founder"] = cand
            break
        if prof["founder"]:
            break

    m = re.search(ROLE_PATTERN, text, re.I)
    if m: prof["role"] = m.group(1)

    m = re.search(YEAR_PATTERN, text, re.I)
    if m: prof["founded"] = m.group(1)

    # published email (prefer info@/contact@ over personal); filter out junk
    emails = re.findall(EMAIL_PATTERN, html)
    clean = []
    for e in emails:
        e = e.strip().lstrip("%20").replace("%20", "")
        el = e.lower()
        # reject image files, tracking hashes, placeholders, sentry/wix noise
        if el.endswith((".png", ".jpg", ".gif", ".svg", ".webp")):
            continue
        if any(junk in el for junk in ["sentry", "wixpress", "example.com", "companyname.com",
                                        "name@", "yourdomain", "email@", "@2x", "sentry-next"]):
            continue
        if len(e.split("@")[0]) > 40:   # hash-like local part
            continue
        clean.append(e)
    if clean:
        generic = [e for e in clean if e.split("@")[0].lower() in
                   ("info", "contact", "hello", "office", "admin", "enquiries", "mail", "meetus")]
        prof["email"] = generic[0] if generic else clean[0]

    m = re.search(r"(https?://[a-z]{2,3}\.linkedin\.com/company/[a-zA-Z0-9\-_]+)", html)
    if m: prof["linkedin"] = m.group(1)

    return prof


def compute_signal(desc: str, prof: dict, full_text: str) -> tuple[str, str]:
    """Return (signal_tier, why_note). Weighted around SPEND / growth-intent signals."""
    t = (desc + " " + full_text).lower()

    # Fit signals
    startup = any(s in t for s in STARTUP)
    boutique = any(s in t for s in BOUTIQUE)
    reg = any(s in t for s in REG)
    large = any(s in t for s in LARGE)
    founder_led = bool(prof.get("founder")) or "founded by" in t or "one-man" in t

    # SPEND / growth-intent signals (the core buying trigger)
    exhibits = any(s in t for s in SPEND_EXHIBIT)
    markets = any(s in t for s in SPEND_MARKETING)
    hiring = any(s in t for s in SPEND_HIRING)
    growth = any(s in t for s in SPEND_GROWTH)
    bd_hire = any(s in t for s in SPEND_BD_HIRE)

    # count distinct spend signals — more independent signals = stronger growth intent
    spend_count = sum([exhibits, markets, hiring, growth])

    score = 0
    reasons = []

    # --- Fit baseline ---
    if reg:         score += 1; reasons.append("regulatory/QA focus")
    if boutique:    score += 1; reasons.append("boutique/specialist")
    if founder_led: score += 1; reasons.append("founder-led")
    if startup:     score += 1; reasons.append("serves startups/SMEs")

    # --- SPEND signals (weighted heavily — this is the buying trigger) ---
    if exhibits: score += 3; reasons.append("exhibits at events (spend signal)")
    if bd_hire:  score += 4; reasons.append("hiring for business development (strong spend signal)")
    elif hiring: score += 2; reasons.append("actively hiring")
    if markets:  score += 2; reasons.append("active marketing/content")
    if growth:   score += 1; reasons.append("growth/BD language")

    # --- Negatives ---
    if large:    score -= 3; reasons.append("larger/established firm")
    if any(x in t for x in ["fully booked", "not accepting", "not taking new", "by referral only",
                            "referral only", "at capacity"]):
        score -= 4; reasons.append("not pursuing outbound (low-fit)")

    # --- Tiering: spend signals gate the top tiers ---
    has_spend = spend_count >= 1 or bd_hire
    if large:
        # HARD CAP: a larger/established firm is not the boutique ICP — never HOT/STRONG,
        # regardless of how many spend signals its (often bigger) marketing shows.
        if score >= 4:
            tier = "✅ GOOD"
        elif score >= 1:
            tier = "⚪ QUALIFY"
        else:
            tier = "❌ LOW FIT"
    elif score >= 7 and has_spend:
        tier = "🔥 HOT"          # strong fit + clear spend/growth investment
    elif score >= 5 and has_spend:
        tier = "⭐ STRONG"        # good fit + some spend signal
    elif score >= 3:
        tier = "✅ GOOD"          # fits profile, weak/no spend signal
    elif score >= 1:
        tier = "⚪ QUALIFY"
    else:
        tier = "❌ LOW FIT"

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

    prof = extract_profile(combined_text, combined_html, row.get("company", "")) if combined_text else empty_profile()

    # WRONG-COMPANY GUARD: if the scraped page doesn't actually match the listed
    # company (redirect / parked / acquired domain), suppress the scraped contact
    # and founder so we don't attach a DIFFERENT company's details.
    company_verified = True
    if combined_text:
        company_verified = verify_company_match(row.get("company", ""), combined_text)
        if not company_verified:
            prof = empty_profile()   # discard wrong-company data
    row["company_verified"] = "yes" if company_verified else "NO - verify manually (site mismatch)"

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


def verify_company_match(company_name: str, combined_text: str) -> bool:
    """Free workaround for the wrong-website bug: confirm the scraped page actually
    belongs to the listed company by checking its distinctive name words appear.
    If not (e.g. a redirect to a different company), we suppress the scraped
    contact/founder data rather than attaching the WRONG company's details."""
    generic = {"ltd", "gmbh", "ag", "inc", "consulting", "consultancy", "group", "the",
               "and", "services", "solutions", "medical", "medtech", "regulatory",
               "quality", "bio", "life", "sciences", "pharma", "limited", "llc", "bv",
               "aps", "ab", "cro", "co", "as"}
    text = combined_text.lower()
    name_words = [w.lower().strip(".,") for w in company_name.split()
                  if w.lower().strip(".,") not in generic and len(w) > 2]
    if not name_words:
        return company_name.lower() in text
    matches = sum(1 for w in name_words if w in text)
    return (matches / len(name_words)) >= 0.5


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
              "founded_year", "public_email", "linkedin", "company_verified", "icp_signals",
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
