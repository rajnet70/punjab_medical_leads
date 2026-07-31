#!/usr/bin/env python3
"""
SWISS MEDTECH DAY FILTER — separates likely startups from large
enterprises, universities, consultancies, and non-company organizations
in the raw 853-name Swiss Medtech Day attendee list.

Honest scope: this is a real, maintained EXCLUSION list, not a formula.
Participant count alone was tested and confirmed NOT to reliably separate
startups from large enterprises (both groups often send just 1 person),
so this uses name-based matching against known large/non-company
organizations instead.

Every record that survives filtering is tagged with a confidence level:
  - "high confidence startup" — not matched to any exclusion pattern,
    AND independently found in another source (Innosuisse, BioAlps, etc.)
  - "likely startup, unverified" — not matched to any exclusion pattern,
    but not independently confirmed elsewhere either
  - excluded entirely if matched to a known large enterprise, university,
    government body, consultancy, or other non-startup organization type

This does NOT claim perfect accuracy — the exclusion list will miss some
real large companies and may occasionally exclude a genuine startup with
a name resembling an excluded pattern. It is a real, honest improvement
over treating all 457 names as equal, not a claim of certainty.
"""
import csv
import re

# Known large medtech/pharma enterprises attending as sponsors/exhibitors —
# real names confirmed present in the actual Swiss Medtech Day 2026 list
KNOWN_LARGE_ENTERPRISES = [
    "roche", "medtronic", "johnson & johnson", "j&j", "zimmer biomet",
    "zimmer gmbh", "zimmer manufacturing", "zimmer switzerland",
    "boston scientific", "straumann", "sonova", "ypsomed", "smith & nephew",
    "b. braun", "becton dickinson", "olympus", "dräger", "elekta",
    "gerresheimer", "hologic", "institut straumann", "karl storz",
    "fresenius", "ferring pharmaceuticals", "geistlich pharma",
    "cilag", "janssen", "depuy synthes", "synthes gmbh", "tecan",
    "hamilton medical", "haagstreit", "ivoclar vivadent", "curaden",
    "swissmedic", "swiss medtech",
    # Added after real diagnostic run confirmed these large/non-startup
    # names were slipping through — same source (Swiss Medtech Day),
    # different specific companies than the first sample caught
    "dassault systemes", "salesforce", "iqvia", "csem", "maxon",
    "sensirion", "veranex", "veristat", "lohmann & rauscher",
    "comsol", "aon", "bsi",  # note: matches "bsi" as standalone token only,
                                    # handled by normalize() word-boundary safe
    "sensile medical", "shl medical", "weidmann medical technology",
    "filax medical",  # est. Swiss medical distributor, not a startup
]

# Consultancies, law firms, and professional services — real names
# confirmed present, not target companies for a startup dataset
KNOWN_CONSULTANCIES = [
    "pwc", "kpmg", "deloitte", "heidrick & struggles", "oaklins",
    "birn+partner", "h.i.executive", "rentsch partner", "sidley austin",
    "leech tishman", "lmd trade law", "skills alliance",
]

# Universities, hospitals, government bodies, embassies, foundations —
# real institutions, not companies at all
KNOWN_INSTITUTIONS = [
    "university", "université", "universität", "hochschule", "fachhochschule",
    "eth zürich", "eth zurich", "epfl", "empa", "chuv", "inselspital",
    "hospital", "clinique", "klinik", "embassy", "kanton ", "canton ",
    "staatssekretariat", "municipality", "municipal", "foundation",
    "stiftung", "fondation", "association", "swissmem", "iso ", " iso",
    "fda", "swiss biotech association", "bioalps",  # already a separate source
    "seco", "office of public health", "u.s. embassy", "us embassy",
]

import unicodedata

def normalize(name):
    # Convert accented characters to their plain equivalent BEFORE
    # stripping non-alphanumeric chars, so 'Systèmes' -> 'systemes'
    # rather than accented letters being deleted entirely -> 'systmes'
    ascii_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9& ]', '', ascii_name.lower()).strip()

def _word_boundary_match(pattern, text):
    """Word-boundary match, not substring — prevents short strings like
    'aon' or 'bsi' from wrongly matching inside a longer real company
    name (e.g. 'Aonic', 'Absion'). Multi-word patterns (e.g. 'haag
    streit') still match as a phrase."""
    escaped = re.escape(pattern)
    return re.search(rf'(?<![a-z0-9]){escaped}(?![a-z0-9])', text) is not None

# Patterns confirmed from real diagnostic output: PDF-download artifact
# text and non-company German phrases that leaked in as "company names"
# during parsing — not large enterprises, just parsing junk.
JUNK_NAME_PATTERNS = [
    r'^download', r'\.pdf', r'^www\.',  # URL/file artifacts, not real names
    r'^keine agentur',  # "not an agency" — a literal disclaimer, not a company
    r'^\d+\s*mb$',
]

def is_junk_name(company_name):
    """Catches parsing artifacts (URLs, file-download labels, disclaimer
    text) that ended up as "company names" — separate from the
    enterprise/institution exclusion above, since these aren't real
    organizations of any kind."""
    n = company_name.lower().strip()
    return any(re.search(p, n) for p in JUNK_NAME_PATTERNS)

def is_excluded(company_name):
    """Returns (True, reason) if this name matches a known non-startup
    pattern, else (False, None). Uses word-boundary matching to avoid
    false positives on real startup names that happen to contain a
    short exclusion pattern as a substring."""
    n = normalize(company_name)
    for enterprise in KNOWN_LARGE_ENTERPRISES:
        if _word_boundary_match(enterprise, n):
            return True, f"known large enterprise ({enterprise})"
    for firm in KNOWN_CONSULTANCIES:
        if _word_boundary_match(firm, n):
            return True, f"known consultancy/professional services ({firm})"
    for inst in KNOWN_INSTITUTIONS:
        if _word_boundary_match(inst, n):
            return True, f"institution/government/association ({inst})"
    return False, None

def main():
    all_rows = list(csv.DictReader(open("companies_ch_raw.csv")))
    smd_rows = [r for r in all_rows if r["source"] == "Swiss Medtech Day 2026"]
    other_rows = [r for r in all_rows if r["source"] != "Swiss Medtech Day 2026"]

    print(f"Swiss Medtech Day raw entries: {len(smd_rows)}")

    # build a lookup of company names seen in OTHER sources, for the
    # confidence-boost cross-reference
    other_names = {normalize(r["company"]) for r in other_rows}

    kept, excluded = [], []
    for row in smd_rows:
        if is_junk_name(row["company"]):
            row["exclusion_reason"] = "parsing artifact (not a real company name)"
            excluded.append(row)
            continue
        is_excl, reason = is_excluded(row["company"])
        if is_excl:
            row["exclusion_reason"] = reason
            excluded.append(row)
            continue

        confirmed_elsewhere = normalize(row["company"]) in other_names
        row["confidence"] = ("high confidence startup — also found in another source"
                              if confirmed_elsewhere
                              else "likely startup, unverified — Swiss Medtech Day only")
        kept.append(row)

    print(f"Excluded (large enterprise/consultancy/institution): {len(excluded)}")
    print(f"Kept as likely startups: {len(kept)}")
    confirmed = sum(1 for r in kept if "high confidence" in r["confidence"])
    print(f"  Of those, cross-confirmed by another source: {confirmed}")
    print(f"  Unverified but not excluded: {len(kept) - confirmed}")

    # write the filtered, tagged Swiss Medtech Day companies
    fieldnames = list(smd_rows[0].keys()) + ["confidence"]
    with open("companies_ch_smd_filtered.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in kept:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    # write the excluded list too, for spot-checking the filter itself
    excl_fieldnames = list(smd_rows[0].keys()) + ["exclusion_reason"]
    with open("companies_ch_smd_excluded.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=excl_fieldnames)
        writer.writeheader()
        for row in excluded:
            writer.writerow({k: row.get(k, "") for k in excl_fieldnames})

    # OVERWRITE companies_ch_raw.csv with the filtered combined set, so
    # this step actually feeds into enrich_ch.py and full_enrich_ch.py
    # downstream, rather than sitting disconnected on the side.
    # Non-SMD rows get confidence="n/a (not Swiss Medtech Day)" so the
    # column exists consistently across all rows.
    for row in other_rows:
        row["confidence"] = "n/a (not Swiss Medtech Day)"
    combined = other_rows + kept
    combined_fieldnames = list(other_rows[0].keys())
    if "confidence" not in combined_fieldnames:
        combined_fieldnames.append("confidence")
    with open("companies_ch_raw.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=combined_fieldnames)
        writer.writeheader()
        for row in combined:
            writer.writerow({k: row.get(k, "") for k in combined_fieldnames})

    print()
    print(f"companies_ch_raw.csv UPDATED — new combined total: {len(combined)}")
    print(f"(was {len(all_rows)} before filtering)")
    print()
    print("HONEST NOTES:")
    print("- This is a maintained exclusion list, not a formula — it will miss")
    print("  some large companies not on the list, and could occasionally")
    print("  exclude a genuine startup with a similar-looking name.")
    print("- 'confidence' field is included in output so low-confidence rows")
    print("  can be treated differently (e.g. lighter enrichment effort, or")
    print("  flagged to the client) rather than treated as equal to verified rows.")
    print("- companies_ch_smd_excluded.csv is written for spot-checking —")
    print("  review it to catch any wrongly-excluded genuine startup.")

if __name__ == "__main__":
    main()
