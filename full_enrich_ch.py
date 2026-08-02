#!/usr/bin/env python3
"""
FULL COMPANY ENRICHMENT — v4, intelligent crawling rebuild.

Root cause of v3's weak fields (Products 1%, Services 0%, Technologies
1%, Specializations 0%): fixed URL guessing (/products, /services) often
doesn't match how a real company site is actually structured, and
heading-based extraction misses content in cards/tiles/grids.

v4 fixes both: discovers real internal links from the homepage, scores
them by business relevance, crawls highest-scoring pages first, and
extracts from the whole page (paragraphs, lists, tables, cards) rather
than only text tied to a matching heading.

Staged per the brief: Discovery -> Crawl -> Content Repository ->
Entity Extraction -> Semantic Classification. Each stage is a separate
function so the crawl diagnostics (stage counts) are real, not inferred.
"""
import csv
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

HEADERS = {"User-Agent": "Mozilla/5.0 (research; leadflow-full/4.0)"}
NA = "N/A"
MAX_PAGES_PER_COMPANY = 12   # sensible crawl limit, per brief section 1
MAX_CRAWL_DEPTH = 2          # homepage -> linked page -> page linked from that

# =================================================================
# PAGE RELEVANCE SCORING (brief section 3)
# =================================================================
HIGH_PRIORITY_WORDS = ["product", "solution", "service", "technology", "application",
                          "capabilit", "industr", "manufactur", "innovation", "platform",
                          "medical device", "quality", "regulatory", "certification"]
MEDIUM_PRIORITY_WORDS = ["team", "leadership", "management", "company", "about",
                            "career", "job", "partner", "distributor"]
LOW_PRIORITY_WORDS = ["news", "press", "contact", "legal", "privacy"]

# NEW: pages that should be EXCLUDED from Products/Services/Technologies/
# Specializations extraction entirely, not just deprioritized. Legal,
# cookie, and privacy pages were confirmed to leak boilerplate text
# ("cookie preferences", "data processing system") into these fields —
# deprioritizing crawl order didn't stop them being crawled and used
# once the crawl limit was reached; this is a genuine exclusion instead.
#
# Careers/jobs pages ADDED after a real run confirmed job-requirement
# text ("Degree in Mechanical Engineering", "Bachelor's or Master's
# degree") was being classified as a company SERVICE, because job
# postings genuinely contain real vocabulary words ("engineering") in
# an unrelated context. Same root cause as the legal-page problem —
# real words appearing on the wrong kind of page.
CONTENT_EXCLUDED_PAGE_PATTERNS = [
    "privacy", "cookie", "legal", "impressum", "terms", "datenschutz",
    "agb", "cgv", "mentions-legales", "gdpr",
    "career", "jobs", "job-", "stellen", "emplois", "vacature",
]

def is_content_excluded_page(url):
    return any(p in url.lower() for p in CONTENT_EXCLUDED_PAGE_PATTERNS)

# NEW: item-level noise filter — catches nav/footer/boilerplate text that
# structurally resembles a "card" or list item (short, matches vocabulary
# by coincidence) but isn't real product/service/technology content.
#
# Email-pattern check ADDED after a real run showed contact emails
# (hans-joerg.dennig@borobotics.ch) leaking directly into the
# Technologies field — a footer/contact card was scanned like any
# other card, with no check that its content was actually contact
# info rather than product content.
import re as _re_noise_check
EMAIL_PATTERN_CHECK = _re_noise_check.compile(r'[\w.\-]+@[\w\-]+\.[a-zA-Z]{2,}')

NOISE_ITEM_PATTERNS = [
    "cookie", "privacy policy", "terms of", "all rights reserved",
    "sign up", "subscribe", "newsletter", "follow us", "copyright",
    "log in", "sign in", "read more", "learn more", "click here",
    "we are looking for", "we're hiring", "apply now", "job description",
    "years of experience", "bachelor's or master", "degree in",
]

def is_noise_item(text):
    lowered = text.lower()
    if EMAIL_PATTERN_CHECK.search(text):
        return True  # contains a raw email — contact info, not commercial content
    return any(p in lowered for p in NOISE_ITEM_PATTERNS)

def score_link(link_text, link_url):
    """Returns an integer relevance score — higher crawls first."""
    combined = (link_text + " " + link_url).lower()
    if any(w in combined for w in HIGH_PRIORITY_WORDS):
        return 3
    if any(w in combined for w in MEDIUM_PRIORITY_WORDS):
        return 2
    if any(w in combined for w in LOW_PRIORITY_WORDS):
        return 1
    return 0  # unscored pages still get crawled if room remains, just last

# =================================================================
# STAGE 1 + 2: DISCOVERY + CRAWLING
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
NON_CONTENT_TAGS = ["script", "style", "noscript", "form"]
# NOTE: nav/footer are NOT stripped entirely in v4 (unlike v3) — the brief
# asks for whole-page extraction including cards/grids, and some sites
# put real content (e.g. a footer product list) there. Boilerplate text
# is still filtered by phrase, just not by wholesale tag removal.

def fetch(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r.text, r.url
    except Exception:
        pass
    return None, None

def is_redirect_stub(cleaned_text):
    stub_phrases = ["click here if the page does not redirect",
                     "you are being redirected", "please wait while you are redirected"]
    lowered = cleaned_text.lower()
    return any(p in lowered for p in stub_phrases) and len(cleaned_text) < 400

def normalize_url(url):
    """Strips fragment/query noise so the same page isn't crawled twice
    under slightly different URLs — brief section 9."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"

def clean_page(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag_name in NON_CONTENT_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    for tag in soup.find_all(attrs={"class": re.compile(r'cookie|gdpr|consent', re.I)}):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    text = BOILERPLATE_RE.sub('', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text, soup

def discover_and_crawl(website):
    """
    Stage 1 (Discovery) + Stage 2 (Crawling) combined: starts at the
    homepage, extracts every internal link, scores them, crawls the
    highest-scoring first, discovers further links recursively up to
    MAX_CRAWL_DEPTH, stops at MAX_PAGES_PER_COMPANY.

    Returns (content_repository, diagnostics) — content_repository is a
    list of (url, cleaned_text, soup) for every page successfully
    crawled; diagnostics tracks counts for the crawl report (brief
    section 11).
    """
    base = website if website.startswith("http") else "https://" + website
    base = base.rstrip("/")
    domain = urlparse(base).netloc

    visited = set()
    content_repository = []
    diagnostics = {"pages_discovered": 0, "pages_crawled": 0, "max_depth_reached": 0,
                    "redirect_stubs_skipped": 0}

    # queue holds (url, depth, score) — sorted by score before each pass
    to_crawl = [(normalize_url(base), 0, 99)]  # homepage always crawled first
    seen_urls = {normalize_url(base)}

    while to_crawl and len(content_repository) < MAX_PAGES_PER_COMPANY:
        to_crawl.sort(key=lambda x: -x[2])  # highest score first
        url, depth, _ = to_crawl.pop(0)
        if url in visited:
            continue
        visited.add(url)

        html, final_url = fetch(url)
        if not html:
            continue
        diagnostics["pages_crawled"] += 1
        diagnostics["max_depth_reached"] = max(diagnostics["max_depth_reached"], depth)

        cleaned_text, soup = clean_page(html)
        if is_redirect_stub(cleaned_text):
            diagnostics["redirect_stubs_skipped"] += 1
            continue

        content_repository.append((url, cleaned_text, soup))

        if depth >= MAX_CRAWL_DEPTH:
            continue

        # discover further internal links from this page
        for a in soup.find_all("a", href=True):
            link_url = urljoin(url, a["href"])
            parsed = urlparse(link_url)
            if parsed.netloc != domain:
                continue  # external link — not this company's own site
            norm = normalize_url(link_url)
            if norm in seen_urls:
                continue
            seen_urls.add(norm)
            diagnostics["pages_discovered"] += 1
            score = score_link(a.get_text(strip=True), link_url)
            to_crawl.append((norm, depth + 1, score))

        time.sleep(0.2)

    return content_repository, diagnostics

# =================================================================
# STAGE 4 + 5: ENTITY EXTRACTION + SEMANTIC CLASSIFICATION
# Operates on the FULL content repository (all crawled pages combined),
# not page-by-page — brief section 10 (Stage 4 description).
# =================================================================

# --- Description ---
NAV_MENU_WORDS = {"home", "about", "team", "contact", "news", "press",
                    "products", "services", "careers", "blog", "login",
                    "menu", "search", "company", "solutions", "resources"}

def _strip_leading_nav_words(text):
    words = text.split()
    idx = 0
    while idx < len(words) and words[idx].lower().strip(",.") in NAV_MENU_WORDS:
        idx += 1
    return " ".join(words[idx:])

def extract_description(repository):
    for url, text, soup in repository:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        for s in sentences:
            s = _strip_leading_nav_words(s.strip())
            if 60 <= len(s) <= 350 and not s.isupper():
                return s
    return None

# --- Products / Services / Technologies / Specializations ---
# v4 approach per brief section 4-5: do NOT depend on a matching heading.
# Instead, scan cards/tiles/list-items/table-cells across the WHOLE page
# for domain-vocabulary matches, classify by vocabulary content rather
# than by which heading they sit under.
PRODUCT_VOCAB = ["device", "platform", "system", "sensor", "implant", "instrument",
                  "software", "kit", "assay", "monitor", "wearable", "prosthetic"]
SERVICE_VOCAB = ["consulting", "engineering", "manufacturing", "regulatory",
                   "validation", "clinical trial", "testing service", "distribution",
                   "training", "support service", "contract manufacturing", "cro service"]
TECH_VOCAB = ["artificial intelligence", "machine learning", "robotics", "cloud",
                "saas", "medical imaging", "cad/cam", "automation", "iot",
                "biosensor", "microfluidics", "spectroscopy", "genomic sequencing",
                "algorithm", "deep learning"]
SPECIALIZATION_VOCAB = ["oncology", "cardiology", "neurology", "orthopedic",
                           "ophthalmology", "dermatology", "immunology", "regulatory affairs",
                           "quality assurance", "clinical research", "biomechanics",
                           "diagnostics expertise", "therapeutic area"]

def _extract_card_like_items(soup):
    """Structural extraction covering cards/tiles/grids/accordions —
    brief section 4: any element with a class hinting at a repeated
    content block, plus standard list items, plus table cells."""
    items = []
    # standard lists
    for li in soup.find_all("li"):
        text = li.get_text(strip=True)
        if 5 <= len(text) <= 150:
            items.append(text)
    # card/tile/grid-like divs — common class name patterns across
    # modern site builders (Webflow, Wix, Squarespace, custom React)
    for tag in soup.find_all(attrs={"class": re.compile(r'card|tile|grid-item|feature|box|accordion', re.I)}):
        text = tag.get_text(strip=True)
        if 5 <= len(text) <= 150:
            items.append(text)
    # table cells
    for td in soup.find_all("td"):
        text = td.get_text(strip=True)
        if 5 <= len(text) <= 150:
            items.append(text)
    return items

def classify_by_vocabulary(repository, vocab):
    """Scans every crawled page's structured items for vocabulary
    matches — classification by content, not by heading label.
    Excludes legal/cookie/privacy pages entirely (genuine noise source,
    confirmed leaking boilerplate into these fields) and filters out
    nav/footer-style noise items even from pages that are kept."""
    matches = []
    for url, text, soup in repository:
        if is_content_excluded_page(url):
            continue  # skip this page entirely for commercial-field extraction
        items = _extract_card_like_items(soup)
        for item in items:
            if is_noise_item(item):
                continue
            lowered = item.lower()
            if any(v in lowered for v in vocab):
                matches.append(item)
        # also check plain paragraph text, not just structured items —
        # covers sites that describe products/services in prose
        for p in soup.find_all("p"):
            p_text = p.get_text(strip=True)
            if is_noise_item(p_text):
                continue
            if 20 <= len(p_text) <= 200 and any(v in p_text.lower() for v in vocab):
                matches.append(p_text)
    # dedupe, preserve order, cap for a clean CSV cell
    seen = set()
    deduped = [m for m in matches if not (m.lower() in seen or seen.add(m.lower()))]
    return "; ".join(deduped[:8]) if deduped else None

# --- Employee count ---
EMPLOYEE_PATTERNS = [
    r'(\d{1,4})\+?\s*(employees|team members|staff|people)',
    r'team of\s*(\d{1,4})',
    r'(\d{1,4})[-–](\d{1,4})\s*employees',
]

def extract_employee_count(repository):
    for url, text, soup in repository:
        for pattern in EMPLOYEE_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return m.group(0).strip()
    return None

# --- Social links ---
SOCIAL_DOMAINS = {
    "linkedin": ["linkedin.com/company", "linkedin.com/in"],
    "facebook": ["facebook.com/"], "twitter": ["twitter.com/", "x.com/"],
    "instagram": ["instagram.com/"], "youtube": ["youtube.com/", "youtu.be/"],
}

def extract_social_links(repository):
    found = {k: None for k in SOCIAL_DOMAINS}
    for url, text, soup in repository:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            for platform, domains in SOCIAL_DOMAINS.items():
                if found[platform]:
                    continue
                if any(d in href for d in domains):
                    found[platform] = href
    return found

# --- Address, parsed into components (brief section 7) ---
POSTAL_CANTON_RANGES = [
    (1000, 1999, "Vaud/Geneva/Valais/Fribourg region"), (2000, 2999, "Neuchâtel/Jura region"),
    (3000, 3999, "Bern region"), (4000, 4999, "Basel region"), (5000, 5999, "Aargau region"),
    (6000, 6999, "Lucerne/Ticino region"), (7000, 7999, "Graubünden region"),
    (8000, 8999, "Zürich region"), (9000, 9999, "St. Gallen/Thurgau region"),
]

def extract_full_address(repository):
    """Checks Contact/Legal/Imprint-style pages preferentially (brief
    section 7), falls back to any page if not found there."""
    priority_pages = [r for r in repository if any(
        kw in r[0].lower() for kw in ["contact", "impressum", "legal", "imprint"])]
    other_pages = [r for r in repository if r not in priority_pages]

    for url, text, soup in priority_pages + other_pages:
        m = re.search(r'\b(CH-)?(\d{4})\s+([A-ZÀ-Ý][a-zà-ÿ]+)\b', text)
        if not m or not (1000 <= int(m.group(2)) <= 9999):
            continue
        city_candidate = m.group(3)
        if city_candidate.lower() in {"home", "about", "contact"}:
            continue
        postal, city = m.group(2), city_candidate
        canton = next((region for lo, hi, region in POSTAL_CANTON_RANGES
                        if lo <= int(postal) <= hi), None)
        street_m = re.search(r'([A-ZÀ-Ý][\wà-ÿ]*(?:strasse|straße|weg|rue|via)\s*\d{1,4}[a-z]?)',
                              text, re.IGNORECASE)
        street = street_m.group(1).strip() if street_m else None
        return street, city, postal, canton
    return None, None, None, None

# --- Contact ---
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

def extract_contact(repository):
    email, phone = None, None
    for url, text, soup in repository:
        if not email:
            candidates = [c for c in EMAIL_RE.findall(text)
                          if c.strip().lower() not in JUNK_EMAILS
                          and not any(re.search(p, c.strip().lower()) for p in JUNK_EMAIL_PATTERNS)]
            if candidates:
                general = [c for c in candidates if c.split("@")[0].lower() in GENERAL_EMAIL_PREFIXES]
                email = general[0] if general else candidates[0]
        if not phone:
            m = PHONE_RE.search(text)
            if m:
                digits = re.sub(r'\D', '', m.group(0))
                if not any(re.match(p, digits) for p in JUNK_PHONE_PATTERNS):
                    phone = m.group(0)
        if email and phone:
            break
    return email, phone

def standardize_phone(phone):
    if not phone:
        return None
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('41') and len(digits) == 11:
        core = digits[2:]
    elif digits.startswith('0') and len(digits) == 10:
        core = digits[1:]
    else:
        return phone.strip()
    return f"+41 {core[0:2]} {core[2:5]} {core[5:7]} {core[7:9]}"

# --- Founders/Leadership (brief section 6) ---
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

def extract_founders(repository):
    """Searches Team/Leadership/Management/About/Company/News/Press
    pages preferentially, per brief section 6."""
    priority_pages = [r for r in repository if any(
        kw in r[0].lower() for kw in ["team", "leadership", "management", "about",
                                        "company", "news", "press"])]
    other_pages = [r for r in repository if r not in priority_pages]

    found = []
    seen_names = set()
    for url, text, soup in priority_pages + other_pages:
        for kw in TITLE_KEYWORDS:
            for m in re.finditer(
                r'([A-Z][a-zà-ÿ]+(?:\s[A-Z][a-zà-ÿ]+){1,2})\s*[,\-–—]\s*(' + re.escape(kw) + r')',
                text, re.IGNORECASE
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
    return found

# --- Funding / founding year ---
FUNDING_PATTERNS = [
    r'rais(?:ed|es|ing)\s+[\w\s]{0,15}?(CHF|USD|EUR|\$|€)\s?[\d.,]+\s?(million|m|k|thousand)?',
    r'(clos(?:ed|es|ing)|secur(?:ed|es|ing))\s+(a|an|its)?\s?[\w\s]{0,20}?(CHF|USD|EUR|\$|€)\s?[\d.,]+\s?(million|m|k)?[\w\s]{0,30}?(round|financing|capital)',
    r'(seed round|series [a-e]|pre-seed)[\w\s,]{0,60}',
    r'backed by\s+[\w\s,&]{5,80}',
    r'(CHF|USD|EUR|\$|€)\s?[\d.,]+\s?(million|m)\s+(in\s+)?(funding|investment|financing|capital)',
    r'venture kick[\w\s,]{0,60}',
]

def extract_funding(repository):
    for url, text, soup in repository:
        for pattern in FUNDING_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                start = m.start()
                while start > 0 and text[start - 1] != ' ':
                    start -= 1
                end = min(len(text), m.end() + 40)
                while end < len(text) and text[end] != ' ':
                    end += 1
                return text[start:end].strip()
    return None

def extract_founding_year(repository):
    for url, text, soup in repository:
        m = re.search(r'founded\s+in\s+(20[0-2]\d|19[89]\d)', text, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r'(since|est\.?)\s+(20[0-2]\d|19[89]\d)', text, re.IGNORECASE)
        if m:
            return m.group(2)
    return None

def extract_linkedin_url(repository):
    for url, text, soup in repository:
        for a in soup.find_all("a", href=True):
            if "linkedin.com/company" in a["href"]:
                return a["href"]
    return None

# --- Sub-sector ---
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

def assign_subsector(description, repository):
    combined = (description or "")
    for url, text, soup in repository[:3]:  # sample first few pages, not everything
        combined += " " + text[:1500]
    lowered = combined.lower()
    scores = {sector: sum(kw in lowered for kw in kws) for sector, kws in SUBSECTOR_KEYWORDS.items()}
    max_score = max(scores.values())
    if max_score == 0:
        return None
    top = [s for s, sc in scores.items() if sc >= max_score - 1 and sc > 0]
    return " / ".join(top[:2])

# --- Hiring intelligence (isolated, brief section 8) ---
JOB_TITLE_HINTS = ["engineer", "scientist", "manager", "director", "analyst",
                     "specialist", "coordinator", "lead", "developer", "researcher",
                     "associate", "intern"]
LOCATION_HINTS = ["remote", "hybrid", "on-site", "onsite"]

def extract_hiring_info(repository):
    careers_pages = [r for r in repository if any(
        kw in r[0].lower() for kw in ["career", "jobs", "job-", "stellen", "emplois"])]
    if not careers_pages:
        return {"hiring_status": None, "careers_url": None, "open_positions_count": None,
                 "job_titles": None, "work_mode": None}

    url, text, soup = careers_pages[0]
    titles_found = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "a", "li"]):
        el_text = el.get_text(strip=True)
        if 5 <= len(el_text) <= 80 and any(h in el_text.lower() for h in JOB_TITLE_HINTS):
            titles_found.append(el_text)
    titles_found = list(dict.fromkeys(titles_found))[:10]

    modes_found = [m for m in LOCATION_HINTS if m in text.lower()]

    return {
        "hiring_status": "Actively hiring" if titles_found else "Careers page found, no open roles listed",
        "careers_url": url,
        "open_positions_count": str(len(titles_found)) if titles_found else None,
        "job_titles": "; ".join(titles_found) if titles_found else None,
        "work_mode": "; ".join(sorted(set(modes_found))) if modes_found else None,
    }

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

def na_if_empty(value):
    if value is None:
        return NA
    if isinstance(value, str) and not value.strip():
        return NA
    return value

# =================================================================
# MAIN — per company: crawl, then extract from the whole repository
# =================================================================
def main():
    all_rows = list(csv.DictReader(open("companies_ch_enriched.csv")))
    rows = [r for r in all_rows if r.get("website", "").strip()]
    print(f"Total companies in file: {len(all_rows)}")
    print(f"Companies with a website (this run's scope): {len(rows)}")

    out_rows = []
    crawl_report_rows = []

    for i, row in enumerate(rows):
        repository, diag = discover_and_crawl(row["website"])

        description = extract_description(repository)
        subsector = assign_subsector(description, repository)
        founders = extract_founders(repository)
        founder_strs = [f"{n}, {t}" for n, t in founders]
        ceo = next((f"{n}, {t}" for n, t in founders
                     if "ceo" in t.lower() or "chief executive" in t.lower()), None)
        funding = extract_funding(repository)
        founding_year = extract_founding_year(repository)
        street, city, postal, canton = extract_full_address(repository)
        email, phone = extract_contact(repository)
        employee_count = extract_employee_count(repository)
        socials = extract_social_links(repository)
        linkedin = extract_linkedin_url(repository)
        products = classify_by_vocabulary(repository, PRODUCT_VOCAB)
        services = classify_by_vocabulary(repository, SERVICE_VOCAB)
        technologies = classify_by_vocabulary(repository, TECH_VOCAB)
        specializations = classify_by_vocabulary(repository, SPECIALIZATION_VOCAB)
        hiring = extract_hiring_info(repository)

        record = {
            "company": row["company"], "website": row["website"],
            "what_they_do": description, "city": city, "canton_region": canton,
            "country": "Switzerland", "postal_code": postal, "street_address": street,
            "founding_year": founding_year, "employee_count": employee_count,
            "sub_sector": subsector, "technologies": technologies, "products": products,
            "services": services, "specializations": specializations,
            "email": email, "phone": standardize_phone(phone),
            "linkedin": linkedin, "facebook": socials["facebook"],
            "twitter_x": socials["twitter"], "instagram": socials["instagram"],
            "youtube": socials["youtube"],
            "founders_and_titles": "; ".join(founder_strs) if founder_strs else None,
            "ceo": ceo, "funding_context": funding,
            "why_relevant": build_why_relevant(description, subsector, founders, funding),
            "hiring_status": hiring["hiring_status"], "careers_url": hiring["careers_url"],
            "open_positions_count": hiring["open_positions_count"],
            "job_titles": hiring["job_titles"], "work_mode": hiring["work_mode"],
            "data_quality_flag": (f"{diag['redirect_stubs_skipped']} redirect stub(s) skipped"
                                    if diag["redirect_stubs_skipped"] else "OK"),
        }
        for k in record:
            record[k] = na_if_empty(record[k])
        out_rows.append(record)

        crawl_report_rows.append({
            "company": row["company"], "pages_discovered": diag["pages_discovered"],
            "pages_crawled": diag["pages_crawled"], "max_depth_reached": diag["max_depth_reached"],
            "products_found": "Y" if products else "N",
            "services_found": "Y" if services else "N",
            "technologies_found": "Y" if technologies else "N",
            "leadership_found": "Y" if founder_strs else "N",
            "contact_found": "Y" if (email != NA or phone != NA) else "N",
            "hiring_found": "Y" if hiring["hiring_status"] else "N",
        })

        if i % 10 == 0:
            print(f"  [{i+1}/{len(rows)}] {row['company']}: "
                  f"pages_crawled={diag['pages_crawled']} desc={'Y' if description else 'N'} "
                  f"products={'Y' if products else 'N'} founders={len(founders)}")

    fieldnames = list(out_rows[0].keys()) if out_rows else []
    with open("companies_ch_222_full.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    crawl_fieldnames = list(crawl_report_rows[0].keys()) if crawl_report_rows else []
    with open("crawl_diagnostics.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=crawl_fieldnames)
        writer.writeheader()
        writer.writerows(crawl_report_rows)

    print(f"\nDone. {len(out_rows)} companies fully processed.")
    for field in fieldnames:
        filled = sum(1 for r in out_rows if r[field] != NA)
        print(f"  {field}: {filled}/{len(out_rows)} ({filled*100//len(out_rows)}%)")
    print(f"\nCrawl diagnostics written to crawl_diagnostics.csv")

if __name__ == "__main__":
    main()
