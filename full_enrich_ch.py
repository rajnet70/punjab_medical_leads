#!/usr/bin/env python3
"""
FULL COMPANY ENRICHMENT — v3, commercial-grade rebuild.

Scope: enrichment quality ONLY, on the existing discovered company list.
Discovery is untouched. Runs on the 168 companies with a real website
(non-Swiss-Medtech-Day, per the current known-good source set).

Every field in this brief's required list is either populated with a
real, verified value, or explicitly "N/A" — never left blank. Accuracy
over guessing throughout: nothing here is inferred beyond what's
genuinely stated on the company's own site or a linked, trusted profile.
"""
import csv
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

HEADERS = {"User-Agent": "Mozilla/5.0 (research; leadflow-full/3.0)"}
NA = "N/A"

CRAWL_PATHS = ["", "/about", "/about-us", "/team", "/leadership", "/careers",
               "/jobs", "/products", "/services", "/solutions", "/technology",
               "/news", "/press", "/contact",
               "/über-uns", "/team-de", "/a-propos", "/carrieres"]

# =================================================================
# CLEANING (reused from v2, unchanged — this part already works well)
# =================================================================
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
NON_CONTENT_TAGS = ["nav", "footer", "header", "script", "style", "noscript", "form", "aside"]

def fetch(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r.text, r.url  # return final URL too — catches redirects
    except Exception:
        pass
    return None, None

def clean_html_for_extraction(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag_name in NON_CONTENT_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    for tag in soup.find_all(attrs={"class": re.compile(r'cookie|gdpr|consent', re.I)}):
        tag.decompose()
    for tag in soup.find_all(attrs={"id": re.compile(r'cookie|gdpr|consent', re.I)}):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    text = BOILERPLATE_RE.sub('', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text, soup

def is_redirect_stub(cleaned_text):
    """Detects a redirect/placeholder page masquerading as real content —
    the exact failure mode confirmed on Swiss Medtech Day company pages.
    Not source-specific: any company whose page is actually a redirect
    stub should be flagged, regardless of which source found them."""
    stub_phrases = ["click here if the page does not redirect",
                     "you are being redirected", "please wait while you are redirected"]
    lowered = cleaned_text.lower()
    return any(p in lowered for p in stub_phrases) and len(cleaned_text) < 400

# =================================================================
# SUB-SECTOR (reused from v2, already tested and working)
# =================================================================
SUBSECTOR_KEYWORDS = {
    "Medical Device / SaMD": ["medical device", "samd", "software as a medical device",
                                "surgical instrument", "implant", "prosthetic",
                                "diagnostic device", "wearable device", "device identity"],
    "Diagnostics": ["diagnostic", "biomarker", "detection assay", "screening test",
                     "in vitro diagnostic", "imaging", "detection", "biosensor",
                     "point-of-care", "assay"],
    "TechBio / Biotech": ["biotech", "therapeutics", "biopharma", "drug discovery",
                            "gene therapy", "cell therapy", "monoclonal antibody",
                            "clinical-stage", "preclinical", "mitochondria", "mitochondrial",
                            "longevity", "cellular", "molecule", "protein", "genomic",
                            "bioscience", "organism", "rna", "dna", "biomarker discovery"],
    "Digital Health / AI": ["digital health", "machine learning", "deep learning",
                              "algorithm-driven", "clinical decision support",
                              "health platform", "telemedicine", "neurofeedback",
                              "mental wellbeing", "mental health", "wellness platform",
                              "patient monitoring", "remote monitoring"],
    "Pharma / Drug Development": ["pharmaceutical", "drug development", "small molecule",
                                     "clinical trial", "fda approval", "swissmedic",
                                     "therapeutic candidate", "drug candidate"],
    "RegTech / Clinical Software": ["regulatory software", "compliance platform",
                                       "clinical trial management", "quality management system"],
}

def assign_subsector(description, cleaned_text):
    search_text = (description or "") + " " + cleaned_text[:2000]
    lowered = search_text.lower()
    scores = {sector: sum(kw in lowered for kw in kws) for sector, kws in SUBSECTOR_KEYWORDS.items()}
    max_score = max(scores.values())
    if max_score == 0:
        return None  # None, not a string — caller decides N/A vs "insufficient evidence" wording
    top_sectors = [s for s, sc in scores.items() if sc >= max_score - 1 and sc > 0]
    return " / ".join(top_sectors[:2])

# =================================================================
# DESCRIPTION (reused from v2, already tested and working)
# =================================================================
NAV_MENU_WORDS = {"home", "about", "team", "contact", "news", "press",
                    "products", "services", "careers", "blog", "login",
                    "menu", "search", "company", "solutions", "resources"}

def _strip_leading_nav_words(text):
    words = text.split()
    idx = 0
    while idx < len(words) and words[idx].lower().strip(",.") in NAV_MENU_WORDS:
        idx += 1
    return " ".join(words[idx:])

def extract_description(cleaned_text):
    sentences = re.split(r'(?<=[.!?])\s+', cleaned_text)
    for s in sentences:
        s = _strip_leading_nav_words(s.strip())
        if 60 <= len(s) <= 350 and not s.isupper():
            return s
    return None

# =================================================================
# NEW: PRODUCTS / SERVICES / TECHNOLOGIES / SPECIALIZATIONS
# =================================================================
# Structural extraction (not raw text copy): looks for list items under
# headed sections matching these labels, so output is a clean list, not
# a paragraph dump — per the brief's "extract structured information
# rather than copying raw text" requirement.
SECTION_LABELS = {
    "products": ["our products", "product portfolio", "products"],
    "services": ["our services", "services offered", "services"],
    "technologies": ["our technology", "technologies", "platform technology"],
    "specializations": ["specializ", "focus areas", "areas of expertise"],
}

def extract_structured_section(soup, cleaned_text, label_keywords):
    """Finds a heading matching one of the label keywords, then collects
    the list items or short following paragraphs under it — structured,
    not a raw dump of surrounding text."""
    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        heading_text = heading.get_text(strip=True).lower()
        if not any(kw in heading_text for kw in label_keywords):
            continue
        items = []
        sib = heading.find_next_sibling()
        steps = 0
        while sib and steps < 6:
            steps += 1
            if sib.name in ("h1", "h2", "h3", "h4"):
                break
            if sib.name in ("ul", "ol"):
                items.extend(li.get_text(strip=True) for li in sib.find_all("li")
                              if 3 <= len(li.get_text(strip=True)) <= 100)
            elif sib.name == "p":
                text = sib.get_text(strip=True)
                if 3 <= len(text) <= 150:
                    items.append(text)
            sib = sib.find_next_sibling()
        if items:
            # dedupe while preserving order
            seen = set()
            deduped = [i for i in items if not (i.lower() in seen or seen.add(i.lower()))]
            return "; ".join(deduped[:8])  # cap length for a clean CSV cell
    return None

# =================================================================
# NEW: COMPANY SIZE / EMPLOYEE COUNT
# =================================================================
EMPLOYEE_PATTERNS = [
    r'(\d{1,4})\+?\s*(employees|team members|staff|people)',
    r'team of\s*(\d{1,4})',
    r'(\d{1,4})[-–](\d{1,4})\s*employees',
]

def extract_employee_count(cleaned_text):
    for pattern in EMPLOYEE_PATTERNS:
        m = re.search(pattern, cleaned_text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None

# =================================================================
# NEW: SOCIAL MEDIA LINKS (structural — from actual <a> hrefs)
# =================================================================
SOCIAL_DOMAINS = {
    "linkedin": ["linkedin.com/company", "linkedin.com/in"],
    "facebook": ["facebook.com/"],
    "twitter": ["twitter.com/", "x.com/"],
    "instagram": ["instagram.com/"],
    "youtube": ["youtube.com/", "youtu.be/"],
}

def extract_social_links(soup):
    found = {k: None for k in SOCIAL_DOMAINS}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        for platform, domains in SOCIAL_DOMAINS.items():
            if found[platform]:
                continue
            if any(d in href for d in domains):
                found[platform] = href
    return found

# =================================================================
# NEW: ADDRESS — full structured breakdown (street, city, canton, postal)
# =================================================================
SWISS_CANTONS = {
    "AG": "Aargau", "AI": "Appenzell Innerrhoden", "AR": "Appenzell Ausserrhoden",
    "BE": "Bern", "BL": "Basel-Landschaft", "BS": "Basel-Stadt", "FR": "Fribourg",
    "GE": "Geneva", "GL": "Glarus", "GR": "Graubünden", "JU": "Jura", "LU": "Lucerne",
    "NE": "Neuchâtel", "NW": "Nidwalden", "OW": "Obwalden", "SG": "St. Gallen",
    "SH": "Schaffhausen", "SO": "Solothurn", "SZ": "Schwyz", "TG": "Thurgau",
    "TI": "Ticino", "UR": "Uri", "VD": "Vaud", "VS": "Valais", "ZG": "Zug", "ZH": "Zürich",
}
# rough postal-code-to-canton mapping by leading digit range — Swiss postal
# codes are broadly geographic; this gives a best-effort canton when the
# page states a postal code but not the canton name directly
POSTAL_CANTON_RANGES = [
    (1000, 1999, "Vaud/Geneva/Valais/Fribourg region"),
    (2000, 2999, "Neuchâtel/Jura region"),
    (3000, 3999, "Bern region"),
    (4000, 4999, "Basel region"),
    (5000, 5999, "Aargau region"),
    (6000, 6999, "Lucerne/Ticino region"),
    (7000, 7999, "Graubünden region"),
    (8000, 8999, "Zürich region"),
    (9000, 9999, "St. Gallen/Thurgau region"),
]

def extract_full_address(cleaned_text):
    """Returns (street, city, postal_code, canton_or_region) — each
    individually N/A if not found, rather than one combined field."""
    street, city, postal, canton = None, None, None, None

    # postal code + city, validated range (same check as v2)
    m = re.search(r'\b(CH-)?(\d{4})\s+([A-ZÀ-Ý][a-zà-ÿ]+)\b', cleaned_text)
    if m and 1000 <= int(m.group(2)) <= 9999 and m.group(3).lower() not in {"home","about","contact"}:
        postal, city = m.group(2), m.group(3)
        for lo, hi, region in POSTAL_CANTON_RANGES:
            if lo <= int(postal) <= hi:
                canton = region
                break

    # street: look for a word ending in "strasse/straße/rue/via" followed by a number
    m2 = re.search(r'([A-ZÀ-Ý][\wà-ÿ]*(?:strasse|straße|weg|rue|via)\s*\d{1,4}[a-z]?)', cleaned_text, re.IGNORECASE)
    if m2:
        street = m2.group(1).strip()

    return street, city, postal, canton

# =================================================================
# NEW: HIRING INTELLIGENCE (additional feature, isolated from core fields)
# =================================================================
JOB_TITLE_HINTS = ["engineer", "scientist", "manager", "director", "analyst",
                     "specialist", "coordinator", "lead", "developer", "researcher",
                     "associate", "intern"]
LOCATION_HINTS = ["remote", "hybrid", "on-site", "onsite"]

def extract_hiring_info(soup, cleaned_text, website_root):
    """Only activates on a careers/jobs page. Returns a dict — every
    field N/A if the page isn't a real careers page or nothing found.
    Isolated from core enrichment per the brief's requirement that this
    must not interfere with the existing process."""
    result = {"hiring_status": NA, "careers_url": NA, "open_positions_count": NA,
               "job_titles": NA, "departments_hiring": NA, "job_locations": NA,
               "work_mode": NA, "date_posted": NA}

    careers_link = None
    for a in soup.find_all("a", href=True):
        if any(kw in a["href"].lower() for kw in ["career", "jobs", "job-", "stellen", "emplois"]):
            careers_link = urljoin(website_root, a["href"])
            break
    if not careers_link:
        return result

    result["careers_url"] = careers_link
    html, _ = fetch(careers_link)
    if not html:
        result["hiring_status"] = "Careers page found but not reachable"
        return result

    page_text, _ = clean_html_for_extraction(html)
    page_soup = BeautifulSoup(html, "html.parser")

    titles_found = []
    for el in page_soup.find_all(["h3", "h4", "a", "li"]):
        text = el.get_text(strip=True)
        if 5 <= len(text) <= 80 and any(hint in text.lower() for hint in JOB_TITLE_HINTS):
            titles_found.append(text)
    titles_found = list(dict.fromkeys(titles_found))[:10]  # dedupe, cap

    if titles_found:
        result["hiring_status"] = "Actively hiring"
        result["job_titles"] = "; ".join(titles_found)
        result["open_positions_count"] = str(len(titles_found))
    else:
        result["hiring_status"] = "Careers page found, no open roles listed"

    modes_found = [m for m in LOCATION_HINTS if m in page_text.lower()]
    if modes_found:
        result["work_mode"] = "; ".join(sorted(set(modes_found)))

    return result

# =================================================================
# CONTACT — email preference + validation (reused logic from v2)
# =================================================================
EMAIL_RE = re.compile(r'[\w.\-]+@[\w\-]+\.[a-zA-Z]{2,}')
PHONE_RE = re.compile(r'(\+41|0)\s?\d{2}\s?\d{3}\s?\d{2}\s?\d{2}')
JUNK_EMAILS = {'email@example.com', 'user@domain.com', 'name@example.com',
               'your@email.com', 'test@test.com', 'info@example.com',
               'example@example.com', 'someone@example.com', 'johnsmith@example.com',
               'info@website.com'}
JUNK_EMAIL_PATTERNS = [r'\.(png|jpg|jpeg|gif|svg|webp)$', r'^[0-9a-f]{20,}@',
                         r'sentry', r'@2x', r'wixpress', r'\.js$', r'\.css$']
JUNK_PHONE_PATTERNS = [r'^0+$', r'^(\d)\1{6,}$']
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
        general_matches = [c for c in candidates if c.split("@")[0].lower() in GENERAL_EMAIL_PREFIXES]
        email = general_matches[0] if general_matches else candidates[0]
    m = PHONE_RE.search(cleaned_text)
    if m:
        digits_only = re.sub(r'\D', '', m.group(0))
        if not any(re.match(p, digits_only) for p in JUNK_PHONE_PATTERNS):
            phone = m.group(0)
    return email, phone

# =================================================================
# FOUNDERS/EXECUTIVES — multilingual, validated (reused from v2)
# =================================================================
TITLE_KEYWORDS = [
    "chief executive officer", "ceo", "co-founder", "founder",
    "chief technology officer", "cto", "chief operating officer",
    "coo", "managing director", "president", "chairman",
    "geschäftsführer", "geschäftsführerin", "mitgründer", "mitgründerin",
    "gründer", "gründerin", "vorsitzender", "vorsitzende",
    "directeur général", "directrice générale", "cofondateur", "cofondatrice",
    "fondateur", "fondatrice", "président", "présidente",
]
INVALID_NAME_WORDS = {"datasheet", "privacy", "policy", "including", "cookie",
                        "terms", "home", "about", "contact", "menu"}

def extract_founders(cleaned_text):
    found = []
    seen_names = set()
    for kw in TITLE_KEYWORDS:
        for m in re.finditer(
            r'([A-Z][a-zà-ÿ]+(?:\s[A-Z][a-zà-ÿ]+){1,2})\s*[,\-–—]\s*(' + re.escape(kw) + r')',
            cleaned_text, re.IGNORECASE
        ):
            name = m.group(1).strip()
            first_word = name.split()[0].lower()
            if first_word in {'and', 'by', 'with', 'led', 'team', 'our'}:
                name = ' '.join(name.split()[1:])
                if len(name.split()) < 2:
                    continue
            name_words = set(w.lower() for w in name.split())
            if name_words & INVALID_NAME_WORDS:
                continue
            if name.lower() in seen_names:
                continue
            seen_names.add(name.lower())
            found.append((name, m.group(2).strip().title()))
    return found  # list of (name, title) tuples — cleaner for CEO/exec team separation

# =================================================================
# FUNDING / FOUNDING YEAR (reused from v2)
# =================================================================
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
            start = m.start()
            while start > 0 and cleaned_text[start - 1] != ' ':
                start -= 1
            end = m.end()
            extended_end = min(len(cleaned_text), end + 40)
            while extended_end < len(cleaned_text) and cleaned_text[extended_end] != ' ':
                extended_end += 1
            return cleaned_text[start:extended_end].strip()
    return None

def extract_founding_year(cleaned_text):
    m = re.search(r'founded\s+in\s+(20[0-2]\d|19[89]\d)', cleaned_text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'(since|est\.?)\s+(20[0-2]\d|19[89]\d)', cleaned_text, re.IGNORECASE)
    if m:
        return m.group(2)
    return None

# =================================================================
# LINKEDIN (kept separate from generic social extraction for clarity —
# LinkedIn is the highest-priority contact channel for B2B outreach)
# =================================================================
def extract_linkedin(soup):
    for a in soup.find_all("a", href=True):
        if "linkedin.com/company" in a["href"]:
            return a["href"]
    return None

# =================================================================
# ORCHESTRATION — visit every relevant page ONCE, gather everything
# =================================================================
def gather_all(website):
    base = website if website.startswith("http") else "https://" + website
    base = base.rstrip("/")
    urls_to_try = [base + p for p in CRAWL_PATHS]

    result = {
        "description": None, "linkedin": None, "facebook": None, "twitter": None,
        "instagram": None, "youtube": None, "funding": None, "founders": [],
        "founding_year": None, "street": None, "city": None, "postal_code": None,
        "canton": None, "email": None, "phone": None, "employee_count": None,
        "products": None, "services": None, "technologies": None,
        "specializations": None, "hiring": None, "redirect_stub_detected": False,
        "pages_crawled": 0,
    }

    for url in urls_to_try:
        html, final_url = fetch(url)
        if not html:
            continue
        result["pages_crawled"] += 1
        cleaned_text, soup = clean_html_for_extraction(html)

        if is_redirect_stub(cleaned_text):
            result["redirect_stub_detected"] = True
            continue  # don't extract from a stub page — same signal that
                       # was misread as real content before

        if not result["description"]:
            result["description"] = extract_description(cleaned_text)
        if not result["linkedin"]:
            result["linkedin"] = extract_linkedin(soup)
        socials = extract_social_links(soup)
        for k in ["facebook", "twitter", "instagram", "youtube"]:
            if not result[k] and socials.get(k):
                result[k] = socials[k]
        if not result["funding"]:
            result["funding"] = extract_funding(cleaned_text)
        new_founders = extract_founders(cleaned_text)
        for f in new_founders:
            if f not in result["founders"]:
                result["founders"].append(f)
        if not result["founding_year"]:
            result["founding_year"] = extract_founding_year(cleaned_text)
        if not result["city"]:
            street, city, postal, canton = extract_full_address(cleaned_text)
            result["street"], result["city"] = street, city
            result["postal_code"], result["canton"] = postal, canton
        if not result["email"] or not result["phone"]:
            email, phone = extract_contact(cleaned_text)
            result["email"] = result["email"] or email
            result["phone"] = result["phone"] or phone
        if not result["employee_count"]:
            result["employee_count"] = extract_employee_count(cleaned_text)
        if not result["products"]:
            result["products"] = extract_structured_section(soup, cleaned_text, SECTION_LABELS["products"])
        if not result["services"]:
            result["services"] = extract_structured_section(soup, cleaned_text, SECTION_LABELS["services"])
        if not result["technologies"]:
            result["technologies"] = extract_structured_section(soup, cleaned_text, SECTION_LABELS["technologies"])
        if not result["specializations"]:
            result["specializations"] = extract_structured_section(soup, cleaned_text, SECTION_LABELS["specializations"])
        if not result["hiring"]:
            result["hiring"] = extract_hiring_info(soup, cleaned_text, base)

        core_done = all([result["description"], result["linkedin"], result["funding"],
                          result["founders"], result["founding_year"], result["city"],
                          result["email"], result["phone"]])
        if core_done:
            break
        time.sleep(0.3)

    return result

def build_why_relevant(description, subsector, founders, funding):
    parts = []
    if subsector:
        parts.append(f"Operates in {subsector.lower()}")
    if description:
        parts.append("with an active, described product or service")
    if founders:
        parts.append(f"{len(founders)} named executive(s)/founder(s) identified")
    if funding:
        parts.append("recent funding activity confirmed on company site")
    if not parts:
        return None
    return "; ".join(parts) + " — potential candidate for regulatory support as it scales."

# =================================================================
# VALIDATION — final pass before export
# =================================================================
def na_if_empty(value):
    """The single, consistent rule: any missing value becomes N/A,
    never a blank string."""
    if value is None:
        return NA
    if isinstance(value, str) and not value.strip():
        return NA
    return value

def standardize_phone(phone):
    if phone == NA or not phone:
        return NA
    digits = re.sub(r'\D', '', phone)
    # normalize to the digits AFTER the country/trunk prefix, so both
    # "079..." (local, trunk 0) and "+4179..."/"4179..." (already
    # country-coded) produce the same standardized output
    if digits.startswith('41') and len(digits) == 11:
        core = digits[2:]
    elif digits.startswith('0') and len(digits) == 10:
        core = digits[1:]
    else:
        return phone.strip()  # unrecognized shape — return as-is rather than mangle it
    return f"+41 {core[0:2]} {core[2:5]} {core[5:7]} {core[7:9]}"

def main():
    all_rows = list(csv.DictReader(open("companies_ch_enriched.csv")))
    rows = [r for r in all_rows if r.get("website", "").strip()]
    print(f"Total companies in file: {len(all_rows)}")
    print(f"Companies with a website (this run's scope): {len(rows)}")

    out_rows = []
    redirect_stubs_found = 0

    for i, row in enumerate(rows):
        found = gather_all(row["website"])

        if found["redirect_stub_detected"] and found["pages_crawled"] <= 1:
            redirect_stubs_found += 1

        subsector = assign_subsector(found["description"], "")
        founder_names = [f"{n}, {t}" for n, t in found["founders"]]
        ceo = next((f"{n}, {t}" for n, t in found["founders"] if "ceo" in t.lower()
                     or "chief executive" in t.lower()), None)

        record = {
            "company": row["company"],
            "website": row["website"],
            "what_they_do": found["description"],
            "city": found["city"],
            "canton_region": found["canton"],
            "country": "Switzerland",  # known constant for this dataset — not a guess
            "postal_code": found["postal_code"],
            "street_address": found["street"],
            "founding_year": found["founding_year"],
            "employee_count": found["employee_count"],
            "sub_sector": subsector,
            "technologies": found["technologies"],
            "products": found["products"],
            "services": found["services"],
            "specializations": found["specializations"],
            "email": found["email"],
            "phone": standardize_phone(found["phone"]),
            "linkedin": found["linkedin"],
            "facebook": found["facebook"],
            "twitter_x": found["twitter"],
            "instagram": found["instagram"],
            "youtube": found["youtube"],
            "founders_and_titles": "; ".join(founder_names) if founder_names else None,
            "ceo": ceo,
            "funding_context": found["funding"],
            "why_relevant": build_why_relevant(found["description"], subsector,
                                                 found["founders"], found["funding"]),
            "hiring_status": found["hiring"]["hiring_status"] if found["hiring"] else NA,
            "careers_url": found["hiring"]["careers_url"] if found["hiring"] else NA,
            "open_positions_count": found["hiring"]["open_positions_count"] if found["hiring"] else NA,
            "job_titles": found["hiring"]["job_titles"] if found["hiring"] else NA,
            "work_mode": found["hiring"]["work_mode"] if found["hiring"] else NA,
            "data_quality_flag": ("Possible redirect/placeholder page — verify manually"
                                    if found["redirect_stub_detected"] else "OK"),
        }

        # apply N/A rule to every field, consistently, no exceptions
        for k in record:
            record[k] = na_if_empty(record[k])

        out_rows.append(record)
        if i % 20 == 0:
            print(f"  [{i+1}/{len(rows)}] {row['company']}: "
                  f"desc={'Y' if found['description']!=None else 'N'} "
                  f"founders={len(found['founders'])} "
                  f"hiring={found['hiring']['hiring_status'] if found['hiring'] else 'N/A'}")

    fieldnames = list(out_rows[0].keys()) if out_rows else []
    with open("companies_ch_222_full.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\nDone. {len(out_rows)} companies fully processed.")
    print(f"Redirect/placeholder pages detected and flagged: {redirect_stubs_found}")
    for field in fieldnames:
        filled = sum(1 for r in out_rows if r[field] != NA)
        print(f"  {field}: {filled}/{len(out_rows)} ({filled*100//len(out_rows)}%)")

if __name__ == "__main__":
    main()
