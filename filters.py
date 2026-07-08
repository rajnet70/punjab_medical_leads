#!/usr/bin/env python3
"""
LeadFlow — ICP Qualification Filters
=====================================
The four filters that turn a raw list of "regulatory consultancies" into a
high-hit-rate list of the ACTUAL ICP: newer, boutique, medical-device
regulatory (MDR/IVDR) firms — not the pharma-adjacent / safety-adjacent /
recruitment / enterprise firms that keyword-matching wrongly lets through.

Derived from real QA findings (Billev 1978, Occams pharmacometrics,
Drive Phase PV pharmacovigilance, Lorit functional-safety, Pharmetheus 100+,
Scandinavian CRO acquired). Each filter encodes one of those lessons.

Returns a verdict per firm: 'fit' | 'flag' | 'drop', plus reasons.
Free — no API, runs on scraped website text.
"""

import re
import datetime

CURRENT_YEAR = datetime.date.today().year

# ---------------------------------------------------------------------------
# FILTER 1 — SPECIALTY (highest impact)
# Keep: genuine medical-device regulatory (MDR/IVDR/ISO 13485/CE/notified body)
# Drop: pharma-adjacent (pharmacovigilance, pharmacometrics), functional-safety,
#       general R&D/process, pure recruitment.
# ---------------------------------------------------------------------------

# Positive: device-regulatory core vocabulary
DEVICE_REG_TERMS = [
    "mdr", "ivdr", "iso 13485", "iso13485", "medical device regulation",
    "in vitro diagnostic", "ce mark", "ce marking", "ce-mark",
    "notified body", "technical documentation", "technical file",
    "eu authorised representative", "eu authorized representative",
    "ec rep", "ch rep", "uk responsible person", "ukrp", "uk rp",
    "medical device", "medical devices", "medtech", "samd",
    "software as a medical device", "eudamed", "swissdamed", "mdsap",
    "510(k)", "510k", "de novo", "iso 14971", "iec 62304", "iec 60601",
]

# Negative: WRONG specialty — these signal a pharma/safety/other-niche firm.
# If a firm is dominated by these and weak on device terms, it's not ICP.
PHARMACOVIGILANCE_TERMS = [
    "pharmacovigilance", "qppv", "signal detection", "adverse event",
    "psur", "pbrer", "dsur", "eudravigilance", "drug safety",
    "safety database", "psmf", "sdea",
]
PHARMACOMETRICS_TERMS = [
    "pharmacometrics", "pk/pd", "pkpd", "population pk", "pharmacokinetic",
    "pharmacodynamic", "clinical pharmacology", "modeling and simulation",
    "modelling and simulation", "nonmem",
]
FUNCTIONAL_SAFETY_TERMS = [
    "iso 26262", "functional safety", "automotive spice", "do-178", "do-254",
    "iec 61508", "iatf 16949", "aerospace", "railway", "agricultural machinery",
    "adas", "battery management",
]
RECRUITMENT_TERMS = [
    "recruit", "recruitment", "talent management", "headhunt", "headhunting",
    "candidates", "job description", "placement", "staffing", "talent hub",
]
# Pure-pharma (drug, not device) regulatory
PHARMA_ONLY_TERMS = [
    "drug regulatory", "drug development", "biologics", "marketing authorisation holder",
    "marketing authorization holder", "cmc", "drug substance", "medicinal product",
]


def score_specialty(text: str) -> tuple[str, str]:
    """Return (verdict, reason). verdict: 'device' | 'adjacent' | 'wrong'."""
    t = text.lower()

    device_hits = sum(1 for k in DEVICE_REG_TERMS if k in t)
    pv_hits = sum(1 for k in PHARMACOVIGILANCE_TERMS if k in t)
    pm_hits = sum(1 for k in PHARMACOMETRICS_TERMS if k in t)
    fs_hits = sum(1 for k in FUNCTIONAL_SAFETY_TERMS if k in t)
    rec_hits = sum(1 for k in RECRUITMENT_TERMS if k in t)
    pharma_hits = sum(1 for k in PHARMA_ONLY_TERMS if k in t)

    wrong_total = pv_hits + pm_hits + fs_hits + pharma_hits

    # Recruitment agency — strong signal it's not a consultancy at all.
    # Drop even if device terms present (recruiters describe device work but
    # place people, they don't do the regulatory work themselves).
    if rec_hits >= 3:
        return ("wrong", f"recruitment agency ({rec_hits} recruiting terms), not a consultancy")

    # Heavy functional-safety = cross-industry safety firm, not device-regulatory.
    # Even with some device terms, dominant FS signals mean wrong core specialty.
    if fs_hits >= 3 and fs_hits >= device_hits:
        return ("wrong", f"functional-safety focus ({fs_hits} FS terms), not device-regulatory")

    # Strong device presence
    if device_hits >= 3:
        # But if a wrong-niche DOMINATES device terms, it's adjacent at best
        if wrong_total > device_hits:
            return ("adjacent", f"device terms ({device_hits}) but dominated by other niche ({wrong_total})")
        return ("device", f"clear device-regulatory focus ({device_hits} device terms)")

    # Weak device, strong wrong-niche → wrong specialty
    if wrong_total >= 2 and device_hits <= 1:
        niche = max([("pharmacovigilance", pv_hits), ("pharmacometrics", pm_hits),
                     ("functional-safety", fs_hits), ("pharma-only", pharma_hits)],
                    key=lambda x: x[1])
        return ("wrong", f"{niche[0]} focus, not medical-device regulatory")

    # Some device terms, not dominant
    if device_hits >= 1:
        return ("adjacent", f"limited device focus ({device_hits} device terms) — verify")

    return ("wrong", "no clear medical-device regulatory focus")


# ---------------------------------------------------------------------------
# FILTER 2 — AGE (catches old institutions: Billev 1978)
# ---------------------------------------------------------------------------
YEAR_PATTERNS = [
    r"(?:founded|established|since|est\.?|inception|in\s+business\s+since|operating\s+since)\s*(?:in\s*)?(19\d\d|20\d\d)",
    r"(\d+)\s*(?:\+\s*)?years?\s+of\s+(?:experience|expertise|excellence)",
]
# Copyright patterns to EXCLUDE (these are NOT founding years)
COPYRIGHT_PATTERN = r"(?:©|copyright|&copy;|all rights reserved)\s*©?\s*(?:19\d\d|20\d\d)"
OLD_THRESHOLD = 2005  # founded before this = likely established institution, flag


def score_age(text: str) -> tuple[str, str, str]:
    """Return (verdict, founding_year, reason). verdict: 'newer'|'old'|'unknown'."""
    t = text.lower()
    years = []

    # Explicit "founded/established/since [year]" only — NOT copyright years
    for m in re.finditer(YEAR_PATTERNS[0], t):
        y = int(m.group(1))
        if 1900 <= y <= CURRENT_YEAR:
            years.append(y)

    # "X years of experience" → infer approximate age
    for m in re.finditer(YEAR_PATTERNS[1], t):
        try:
            n = int(m.group(1))
            if 15 <= n <= 130:
                years.append(CURRENT_YEAR - n)
        except ValueError:
            pass

    if not years:
        return ("unknown", "", "founding year not stated")

    founded = min(years)
    # sanity: a "founding year" equal to the current year is almost always a
    # copyright/date artifact, not a real founding — ignore it
    if founded >= CURRENT_YEAR:
        return ("unknown", "", "no reliable founding year (current-year artifact)")
    if founded < OLD_THRESHOLD:
        return ("old", str(founded), f"established institution (founded {founded})")
    return ("newer", str(founded), f"newer firm (founded {founded})")


# ---------------------------------------------------------------------------
# FILTER 3 — SIZE (catches Pharmetheus 100+, Alacrita 350+, QbD 600+)
# Website proxies only; explicit size field auto-set to 'verify' for the human.
# ---------------------------------------------------------------------------
LARGE_SIGNALS = [
    "worldwide", "global offices", "offices across", "on six continents",
    "multinational", "professionals worldwide", "20+ offices", "25+ locations",
    "global organizations", "global organisations", "600 professionals",
    "hundreds of employees", "global team", "global presence", "our offices in",
    "network of over", "specialist network", "3,000", "over 100 employees",
    "100+ employees", "leading consultancy", "leading global", "offices in",
    "countries worldwide", "across the globe", "global leader", "fortune 500",
    "big four", "big 4", "thousands of", "40 countries", "50 countries",
    "member firms", "our global", "world's leading",
]
# Known enterprise firms that must never pass as boutique
KNOWN_LARGE = [
    "ernst & young", "ey.com", "deloitte", "kpmg", "pwc", "pricewaterhouse",
    "accenture", "mckinsey", "iqvia", "parexel", "icon plc", "labcorp",
    "thermo fisher", "ul solutions", "emergo by ul", "sgs", "tüv", "tuv ",
    "bureau veritas", "intertek", "nsf international", "qserve group",
    "veranex", "aurevia", "qbd group",
]
BOUTIQUE_SIGNALS = [
    "boutique", "small team", "small and specialised", "small and specialized",
    "hands-on", "personalised", "personalized", "founder-led", "one-man",
    "we are a small", "tailored", "dedicated team of", "independent consultancy",
]


def score_size(text: str) -> tuple[str, str]:
    """Return (verdict, reason). verdict: 'boutique'|'large'|'verify'."""
    t = text.lower()

    # Known enterprise names — hard large
    for name in KNOWN_LARGE:
        if name in t:
            return ("large", f"known enterprise firm ({name})")

    large = sum(1 for k in LARGE_SIGNALS if k in t)
    boutique = sum(1 for k in BOUTIQUE_SIGNALS if k in t)

    if large >= 2:
        return ("large", f"large-firm signals present ({large})")
    if large >= 1 and boutique == 0:
        return ("large", "shows scale/global-footprint language")
    if boutique >= 1:
        return ("boutique", "boutique/small-team language")
    return ("verify", "size not clear — verify on LinkedIn")


# ---------------------------------------------------------------------------
# FILTER 4 — STATUS (catches acquired: Scandinavian CRO, QAdvis, Medidee)
# ---------------------------------------------------------------------------
ACQUIRED_SIGNALS = [
    "acquired by", "now part of veranex", "part of veranex", "an aurevia company",
    "part of the aurevia", "now part of the", "has been acquired", "was acquired",
    "a subsidiary of", "wholly owned subsidiary", "now part of aurevia",
    "part of the veranex", "joined forces with", "has merged with", "merged into",
    "now trading as part of", "a company of the",
]
# Guard phrases — if the "part of" is one of these innocent uses, it's NOT acquisition
ACQUIRED_FALSE_FRIENDS = [
    "part of our", "part of the team", "part of the process", "part of the solution",
    "part of your", "part of the journey", "part of a comprehensive", "be part of",
    "part of the eu", "part of the world", "part of the value", "part of the family",
]


def score_status(text: str) -> tuple[str, str]:
    """Return (verdict, reason). verdict: 'independent'|'acquired'."""
    t = text.lower()
    for sig in ACQUIRED_SIGNALS:
        if sig in t:
            # make sure it's not an innocent "part of our team" style phrase
            idx = t.find(sig)
            window = t[max(0, idx - 5):idx + len(sig) + 15]
            if any(ff in window for ff in ACQUIRED_FALSE_FRIENDS):
                continue
            return ("acquired", f"appears acquired/part of larger group ('{sig}')")
    return ("independent", "independent")


# ---------------------------------------------------------------------------
# COMBINE — overall verdict from the four filters
# ---------------------------------------------------------------------------
def qualify(text: str) -> dict:
    """Run all four filters, return combined verdict + per-filter detail."""
    spec_v, spec_r = score_specialty(text)
    age_v, year, age_r = score_age(text)
    size_v, size_r = score_size(text)
    stat_v, stat_r = score_status(text)

    # Decision logic
    # DROP if: wrong specialty, acquired, old institution, or clearly large
    if stat_v == "acquired":
        verdict = "drop"; why = stat_r
    elif spec_v == "wrong":
        verdict = "drop"; why = spec_r
    elif age_v == "old":
        verdict = "drop"; why = age_r
    elif size_v == "large":
        verdict = "drop"; why = size_r
    # FLAG if: adjacent specialty, or size unverified, or age unknown
    elif spec_v == "adjacent":
        verdict = "flag"; why = f"borderline specialty — {spec_r}"
    elif size_v == "verify":
        verdict = "flag"; why = "verify size on LinkedIn"
    # FIT otherwise
    else:
        verdict = "fit"; why = "device-regulatory, newer, boutique, independent"

    return {
        "verdict": verdict,
        "why": why,
        "specialty": spec_v,
        "specialty_reason": spec_r,
        "founding_year": year,
        "age": age_v,
        "size": size_v,
        "status": stat_v,
    }
