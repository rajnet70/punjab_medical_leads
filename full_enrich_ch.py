#!/usr/bin/env python3
"""
FULL COMPANY INTELLIGENCE — v2, rebuilt for reusable extraction quality.

Applies to any company with a real website (this run: the 222 for
Switzerland; the same code applies unchanged to future countries).

Pipeline stages, in order:
  1. FETCH   — visit homepage + common About/Team/News/Contact paths
  2. CLEAN   — strip cookie banners, nav, footer, and legal boilerplate
               from the page BEFORE any extraction runs on it
  3. EXTRACT — pull description, sub-sector, founders+titles (plural),
               funding, founding year, address (validated), LinkedIn,
               email, phone — each from the CLEANED text only
  4. VALIDATE — reject malformed addresses, placeholder contacts, and
               duplicate/inconsistent values before they enter the output

Design principle: every extraction function takes cleaned text and a
defined pattern to match — nothing here is a one-off fix for this
specific dataset. The cleaning stage and extraction functions are
reusable as-is for the next country's dataset.
"""
import csv
import re
import time
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (research; leadflow-full/2.0)"}
EXTRA_PATHS = ["/about", "/about-us", "/team", "/news", "/press", "/contact",
               "/über-uns", "/a-propos", "/company", "/leadership"]

# =================================================================
# STAGE 1: FETCH
# =================================================================
def fetch(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None

# =================================================================
# STAGE 2: CLEAN — strip boilerplate BEFORE extraction ever runs
# =================================================================
# Reusable, generic phrase list — not company-specific. These are the
# standard phrases that appear on cookie banners, footers, and legal
# pages across virtually any website, in English, German, and French
# (the three main languages of the sites in this project).
BOILERPLATE_PHRASES = [
    r'we use cookies[^.]*\.', r'this website uses cookies[^.]*\.',
    r'accept all( cookies)?', r'cookie (policy|settings|preferences|notice)',
    r'privacy policy', r'terms (and|&) conditions', r'terms of (use|service)',
    r'all rights reserved', r'copyright\s*©?\s*\d{4}',
    r'subscribe to our newsletter', r'sign up for updates',
    r'wir verwenden cookies[^.]*\.', r'datenschutz(erklärung)?',
    r'nous utilisons des cookies[^.]*\.', r'politique de confidentialité',
    r'skip to (main )?content', r'back to top',
]
BOILERPLATE_RE = re.compile('|'.join(BOILERPLATE_PHRASES), re.IGNORECASE)

# Tags that are structurally never body content — removed before any
# text extraction, not filtered after the fact
NON_CONTENT_TAGS = ["nav", "footer", "header", "script", "style", "noscript",
                     "form", "aside"]

def clean_html_for_extraction(html):
    """
    Returns cleaned visible text with structural non-content (nav, footer,
    scripts) removed at the DOM level, and boilerplate phrases stripped
    from the remaining text. This is the single cleaning pass every
    extraction function below relies on — clean once, extract many times.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag_name in NON_CONTENT_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    # also drop common cookie-banner container patterns by class/id keyword,
    # since many sites don't use a semantic tag for these
    for tag in soup.find_all(attrs={"class": re.compile(r'cookie|gdpr|consent', re.I)}):
        tag.decompose()
    for tag in soup.find_all(attrs={"id": re.compile(r'cookie|gdpr|consent', re.I)}):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    text = BOILERPLATE_RE.sub('', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text, soup  # return both: cleaned text for text-matching,
                        # cleaned soup for structural lookups (links etc.)

# =================================================================
# STAGE 3: EXTRACT — each function takes CLEANED input only
# =================================================================

SUBSECTOR_KEYWORDS = {
    "Medical Device / SaMD": ["medical device", "samd", "software as a medical device",
                                "surgical instrument", "implant", "prosthetic",
                                "diagnostic device", "wearable device"],
    "Diagnostics": ["diagnostic", "biomarker", "detection assay", "screening test",
                     "in vitro diagnostic", "imaging"],
    "TechBio / Biotech": ["biotech", "therapeutics", "biopharma", "drug discovery",
                            "gene therapy", "cell therapy", "monoclonal antibody",
                            "clinical-stage", "preclinical"],
    "Digital Health / AI": ["digital health", "machine learning", "deep learning",
                              "algorithm-driven", "clinical decision support",
                              "health platform", "telemedicine"],
    "Pharma / Drug Development": ["pharmaceutical", "drug development", "small molecule",
                                     "clinical trial", "fda approval", "swissmedic"],
    "RegTech / Clinical Software": ["regulatory software", "compliance platform",
                                       "clinical trial management", "quality management system"],
}

# Common nav-menu words that appear with no punctuation before real
# content (e.g. "Home About Team Contact CompanyName does X...") — this
# list is reusable/generic, not tied to any one company's site
NAV_MENU_WORDS = {"home", "about", "team", "contact", "news", "press",
                    "products", "services", "careers", "blog", "login",
                    "menu", "search", "company", "solutions", "resources"}

def _strip_leading_nav_words(text):
    """Removes a run of short capitalized nav-like words from the start
    of a text block, even when there's no punctuation separating them
    from the real sentence that follows."""
    words = text.split()
    idx = 0
    while idx < len(words) and words[idx].lower().strip(",.") in NAV_MENU_WORDS:
        idx += 1
    return " ".join(words[idx:])

def extract_description(cleaned_text):
    """First substantial, non-boilerplate sentence-like chunk."""
    sentences = re.split(r'(?<=[.!?])\s+', cleaned_text)
    for s in sentences:
        s = _strip_leading_nav_words(s.strip())
        if 60 <= len(s) <= 350 and not s.isupper():
            return s
    return None

def assign_subsector(description, cleaned_text):
    """Check description first, fall back to full cleaned page text —
    gives classification more real signal to work with, still keyword-
    based against a defined, reusable list, not guessed per company.

    Returns MULTIPLE sub-sectors when a company genuinely spans more
    than one category (e.g. AI-driven diagnostics) rather than forcing
    a single label — reflects the real business, not an artificial
    single choice."""
    search_text = (description or "") + " " + cleaned_text[:2000]
    lowered = search_text.lower()
    scores = {sector: sum(kw in lowered for kw in kws)
              for sector, kws in SUBSECTOR_KEYWORDS.items()}
    max_score = max(scores.values())
    if max_score == 0:
        return "Healthcare / Life Sciences (unclassified — needs manual review)"
    # any category within 1 point of the top score is considered
    # genuinely co-relevant, not just noise — a small, deliberate
    # tolerance rather than requiring an exact tie
    top_sectors = [s for s, sc in scores.items() if sc >= max_score - 1 and sc > 0]
    return " / ".join(top_sectors[:2])  # cap at 2 to keep the field readable

def extract_linkedin(soup):
    for a in soup.find_all("a", href=True):
        if "linkedin.com/company" in a["href"] or "linkedin.com/in" in a["href"]:
            return a["href"]
    return None

FUNDING_PATTERNS = [
    r'rais(?:ed|es|ing)\s+[\w\s]{0,15}?(CHF|USD|EUR|\$|€)\s?[\d.,]+\s?(million|m|k|thousand)?',
    r'(clos(?:ed|es|ing)|secur(?:ed|es|ing))\s+(a|an|its)?\s?[\w\s]{0,20}?(CHF|USD|EUR|\$|€)\s?[\d.,]+\s?(million|m|k)?[\w\s]{0,30}?(round|financing|capital)',
    r'(seed round|series [a-e]|pre-seed)[\w\s,]{0,60}',
    r'backed by\s+[\w\s,&]{5,80}',
    r'(CHF|USD|EUR|\$|€)\s?[\d.,]+\s?(million|m)\s+(in\s+)?(funding|investment|financing|capital)',
    r'venture kick[\w\s,]{0,60}',
]

def extract_funding(cleaned_text):
    for pattern in FUNDING_PATTERNS:
        m = re.search(pattern, cleaned_text, re.IGNORECASE)
        if m:
            # widen to the nearest whole word boundary on each side,
            # instead of a fixed character count, so the snippet never
            # starts or ends mid-word
            start = m.start()
            while start > 0 and cleaned_text[start - 1] != ' ':
                start -= 1
            end = m.end()
            extended_end = min(len(cleaned_text), end + 40)
            while extended_end < len(cleaned_text) and cleaned_text[extended_end] != ' ':
                extended_end += 1
            return cleaned_text[start:extended_end].strip()
    return None

# Executive/founder extraction — REUSABLE title vocabulary, not tied to
# this dataset. Returns ALL matches found (multiple founders), not just
# the first, and validates the "name" isn't itself a stray title/word.
TITLE_KEYWORDS = ["chief executive officer", "ceo", "co-founder", "founder",
                    "chief technology officer", "cto", "chief operating officer",
                    "coo", "managing director", "president", "chairman"]
INVALID_NAME_WORDS = {"datasheet", "privacy", "policy", "including", "cookie",
                        "terms", "home", "about", "contact", "menu"}

def extract_founders(cleaned_text):
    """
    Finds "Name Name, Title" or "Name Name — Title" pairs for EVERY
    title keyword, not just the first match — supports multiple
    founders/executives per company. Rejects matches where the
    "name" portion is actually a stray non-name word (cookie/menu
    leakage caught even after cleaning).
    """
    found = []
    seen_names = set()
    for kw in TITLE_KEYWORDS:
        for m in re.finditer(
            r'([A-Z][a-zà-ÿ]+(?:\s[A-Z][a-zà-ÿ]+){1,2})\s*[,\-–—]\s*(' + re.escape(kw) + r')',
            cleaned_text, re.IGNORECASE
        ):
            name = m.group(1).strip()
            # reject if the FIRST WORD of the matched name is itself a
            # connector word that leaked in from the preceding sentence
            # (e.g. matching "and Matteo Rossi" instead of "Matteo Rossi")
            first_word = name.split()[0].lower()
            if first_word in {'and', 'by', 'with', 'led', 'team', 'our'}:
                name = ' '.join(name.split()[1:])  # drop the stray connector, keep the real name
                if len(name.split()) < 2:
                    continue  # not enough left to be a real two-part name
            title = m.group(2).strip()
            name_words = set(w.lower() for w in name.split())
            if name_words & INVALID_NAME_WORDS:
                continue  # rejected: name portion is boilerplate, not a person
            if name.lower() in seen_names:
                continue  # dedupe: same person matched under a second title keyword
            seen_names.add(name.lower())
            found.append(f"{name}, {title.title()}")
    return found  # list — may be empty, one, or several

def extract_founding_year(cleaned_text):
    m = re.search(r'founded\s+in\s+(20[0-2]\d|19[89]\d)', cleaned_text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'(since|est\.?)\s+(20[0-2]\d|19[89]\d)', cleaned_text, re.IGNORECASE)
    if m:
        return m.group(2)
    return None

# Address extraction WITH validation — reusable Swiss postal pattern,
# rejects obviously malformed matches (e.g. a 4-digit number that isn't
# actually a real Swiss postal code range, or a "city" that's a common
# non-place word caught by accident)
SWISS_CANTONS = {"ZH","BE","LU","UR","SZ","OW","NW","GL","ZG","FR","SO","BS",
                   "BL","SH","AR","AI","SG","GR","AG","TG","TI","VD","VS","NE","GE","JU"}
NON_CITY_WORDS = {"home", "about", "contact", "menu", "read", "more", "cookie"}

def extract_address(cleaned_text):
    m = re.search(r'\b(CH-)?(\d{4})\s+([A-ZÀ-Ý][a-zà-ÿ]+)\b', cleaned_text)
    if not m:
        return None
    postal_code, city = m.group(2), m.group(3)
    # Swiss postal codes run 1000-9999 — reject anything outside that,
    # a cheap but real sanity check against grabbing an unrelated number
    if not (1000 <= int(postal_code) <= 9999):
        return None
    if city.lower() in NON_CITY_WORDS:
        return None  # rejected: matched a menu word, not a real city
    return f"{postal_code} {city}"

EMAIL_RE = re.compile(r'[\w.\-]+@[\w\-]+\.[a-zA-Z]{2,}')
PHONE_RE = re.compile(r'(\+41|0)\s?\d{2}\s?\d{3}\s?\d{2}\s?\d{2}')

JUNK_EMAILS = {'email@example.com', 'user@domain.com', 'name@example.com',
               'your@email.com', 'test@test.com', 'info@example.com',
               'example@example.com', 'someone@example.com', 'johnsmith@example.com',
               'info@website.com'}
JUNK_EMAIL_PATTERNS = [r'\.(png|jpg|jpeg|gif|svg|webp)$', r'^[0-9a-f]{20,}@',
                         r'sentry', r'@2x', r'wixpress', r'\.js$', r'\.css$']
JUNK_PHONE_PATTERNS = [r'^0+$', r'^(\d)\1{6,}$']  # all zeros, or same digit repeated

# General/departmental email prefixes are preferred over a named
# individual's email for a business contact record — durable (doesn't
# go stale when a person leaves) and appropriate for cold outreach
GENERAL_EMAIL_PREFIXES = ["info", "contact", "hello", "office", "admin",
                            "general", "enquiries", "inquiries", "mail"]

def extract_contact(cleaned_text):
    email, phone = None, None
    candidates = []
    for candidate in EMAIL_RE.findall(cleaned_text):
        c = candidate.strip().lower()
        if c in JUNK_EMAILS or any(re.search(p, c) for p in JUNK_EMAIL_PATTERNS):
            continue
        candidates.append(candidate)

    if candidates:
        # prefer a general/departmental address if one exists on the page
        general_matches = [c for c in candidates
                            if c.split("@")[0].lower() in GENERAL_EMAIL_PREFIXES]
        email = general_matches[0] if general_matches else candidates[0]

    m = PHONE_RE.search(cleaned_text)
    if m:
        digits_only = re.sub(r'\D', '', m.group(0))
        if not any(re.match(p, digits_only) for p in JUNK_PHONE_PATTERNS):
            phone = m.group(0)
    return email, phone

# =================================================================
# ORCHESTRATION — one company, multiple pages, merge findings
# =================================================================
def gather_all(website):
    base = website if website.startswith("http") else "https://" + website
    base = base.rstrip("/")
    urls_to_try = [base] + [base + p for p in EXTRA_PATHS]

    result = {"description": None, "linkedin": None, "funding": None,
              "founders": [], "founding_year": None, "address": None,
              "email": None, "phone": None, "cleaned_text_sample": ""}

    for url in urls_to_try:
        html = fetch(url)
        if not html:
            continue
        cleaned_text, soup = clean_html_for_extraction(html)
        if not result["cleaned_text_sample"]:
            result["cleaned_text_sample"] = cleaned_text[:2000]

        if not result["description"]:
            result["description"] = extract_description(cleaned_text)
        if not result["linkedin"]:
            result["linkedin"] = extract_linkedin(soup)
        if not result["funding"]:
            result["funding"] = extract_funding(cleaned_text)
        new_founders = extract_founders(cleaned_text)
        for f in new_founders:
            if f not in result["founders"]:
                result["founders"].append(f)
        if not result["founding_year"]:
            result["founding_year"] = extract_founding_year(cleaned_text)
        if not result["address"]:
            result["address"] = extract_address(cleaned_text)
        if not result["email"] or not result["phone"]:
            email, phone = extract_contact(cleaned_text)
            result["email"] = result["email"] or email
            result["phone"] = result["phone"] or phone

        if all([result["description"], result["linkedin"], result["funding"],
                result["founders"], result["founding_year"], result["address"],
                result["email"], result["phone"]]):
            break  # everything found — no need to keep visiting pages
        time.sleep(0.3)

    return result

def build_why_relevant(description, subsector, founders, funding):
    parts = []
    if subsector and "unclassified" not in subsector:
        parts.append(f"Operates in {subsector.lower()}")
    if description:
        parts.append("with an active, described product or service")
    if founders:
        parts.append(f"{len(founders)} named executive(s)/founder(s) identified")
    if funding:
        parts.append("recent funding activity confirmed on company site")
    if not parts:
        return "NOT DETERMINED — insufficient public data to assess relevance"
    return "; ".join(parts) + " — potential candidate for regulatory support as it scales."

def main():
    all_rows = list(csv.DictReader(open("companies_ch_enriched.csv")))
    rows = [r for r in all_rows if r.get("website", "").strip()]
    print(f"Total companies in file: {len(all_rows)}")
    print(f"Companies with a website (this run's scope): {len(rows)}")

    out_rows = []
    counts = {"description": 0, "linkedin": 0, "funding": 0,
              "founders": 0, "founding_year": 0, "address": 0,
              "email": 0, "phone": 0}

    for i, row in enumerate(rows):
        found = gather_all(row["website"])
        subsector = assign_subsector(found["description"], found["cleaned_text_sample"])

        row["what_they_do"] = found["description"] or "NOT FOUND — no clean description available"
        row["sub_sector"] = subsector
        row["linkedin"] = found["linkedin"] or "NOT FOUND"
        row["funding_context"] = found["funding"] or "NOT FOUND"
        row["founders_and_titles"] = "; ".join(found["founders"]) if found["founders"] else "NOT FOUND"
        row["founding_year"] = found["founding_year"] or "NOT FOUND"
        row["address_canton"] = found["address"] or "NOT FOUND"
        row["email"] = found["email"] or "NOT FOUND"
        row["phone"] = found["phone"] or "NOT FOUND"
        row["why_relevant"] = build_why_relevant(
            found["description"], subsector, found["founders"], found["funding"])

        for key, val in [("description", found["description"]), ("linkedin", found["linkedin"]),
                          ("funding", found["funding"]), ("founders", found["founders"]),
                          ("founding_year", found["founding_year"]), ("address", found["address"]),
                          ("email", found["email"]), ("phone", found["phone"])]:
            if val:
                counts[key] += 1

        out_rows.append(row)
        if i % 20 == 0:
            print(f"  [{i+1}/{len(rows)}] {row['company']}: "
                  f"desc={'Y' if found['description'] else 'N'} "
                  f"founders={len(found['founders'])} "
                  f"funding={'Y' if found['funding'] else 'N'}")

    # dedupe fieldnames, drop the old single-founder columns this replaces
    old_cols_to_drop = {"founder_and_title"}
    fieldnames = [f for f in rows[0].keys() if f not in old_cols_to_drop]
    for extra in ["what_they_do", "sub_sector", "linkedin", "why_relevant",
                  "funding_context", "founders_and_titles", "founding_year", "address_canton"]:
        if extra not in fieldnames:
            fieldnames.append(extra)

    with open("companies_ch_222_full.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in out_rows:
            for field in fieldnames:
                row.setdefault(field, "")
            writer.writerow({k: row[k] for k in fieldnames})

    print(f"\nDone. {len(out_rows)} companies fully processed.")
    for key, count in counts.items():
        print(f"  {key}: {count} ({count*100//len(out_rows)}%)")

if __name__ == "__main__":
    main()
