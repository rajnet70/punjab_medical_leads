import requests
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import time
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

API_KEY = os.environ.get("GOOGLE_API_KEY", "")
OUTPUT_DIR = "output"
CITY = "Faisalabad"

FAISALABAD_ZONES = [
    {"name": "City Center",    "lat": 31.4180, "lng": 73.0790},
    {"name": "Clock Tower",    "lat": 31.4154, "lng": 73.0839},
    {"name": "Peoples Colony", "lat": 31.4350, "lng": 73.0780},
    {"name": "Gulberg",        "lat": 31.4450, "lng": 73.0900},
    {"name": "Madina Town",    "lat": 31.4280, "lng": 73.1050},
    {"name": "Johar Town",     "lat": 31.4050, "lng": 73.0950},
    {"name": "Jinnah Colony",  "lat": 31.4000, "lng": 73.0700},
    {"name": "Samanabad",      "lat": 31.4300, "lng": 73.0600},
    {"name": "Canal Road",     "lat": 31.4500, "lng": 73.1100},
    {"name": "Satiana Road",   "lat": 31.3900, "lng": 73.0800},
    {"name": "Sargodha Road",  "lat": 31.4600, "lng": 73.0700},
    {"name": "Jaranwala Road", "lat": 31.4100, "lng": 73.1200},
    {"name": "Millat Road",    "lat": 31.4400, "lng": 73.1300},
    {"name": "Susan Road",     "lat": 31.4650, "lng": 73.1000},
    {"name": "Dijkot Road",    "lat": 31.3800, "lng": 73.0600},
]

DOCTOR_QUERIES = ["doctor", "clinic", "hospital", "specialist", "medical center"]
RADIUS = 1500

REMOVE_KEYWORDS = [
    "vet", "veterinar", "homeopath", "homoeopath",
    "animal hospital", "animal clinic", "hakeem", "hakim",
    "unani", "tibb", "dawakhana", "physiother"
]

SPECIALTY_MAP = [
    (["cardiac", "heart", "cardio"],                     "Cardiologist"),
    (["eye", "ophthal", "vision", "optical"],            "Eye Specialist"),
    (["child", "pediatric", "paediat", "children"],      "Pediatrician"),
    (["skin", "dermat"],                                  "Dermatologist"),
    (["bone", "ortho"],                                   "Orthopedic"),
    (["neuro", "brain"],                                  "Neurologist"),
    (["gynae", "gyneco", "obstet", "maternity", "women"],"Gynecologist"),
    (["dental", "dentist", "teeth", "tooth"],             "Dentist"),
    (["ent", "ear", "nose", "throat"],                    "ENT Specialist"),
    (["urol", "kidney", "renal"],                         "Urologist"),
    (["psychiat", "mental health"],                       "Psychiatrist"),
    (["surgeon", "surgery", "surgical"],                  "Surgeon"),
    (["diabetes", "diabetic", "endocrin"],                "Endocrinologist"),
    (["gastro", "stomach", "liver", "hepat"],             "Gastroenterologist"),
]


def nearby_search(lat, lng, keyword):
    results = []
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": RADIUS,
        "keyword": keyword,
        "key": API_KEY
    }
    for _ in range(3):
        try:
            r = requests.get(url, params=params, timeout=15)
            data = r.json()
            status = data.get("status")
            if status == "REQUEST_DENIED":
                log.error(f"API key error: {data.get('error_message')}")
                return results
            if status not in ("OK", "ZERO_RESULTS"):
                break
            results.extend(data.get("results", []))
            next_token = data.get("next_page_token")
            if not next_token:
                break
            time.sleep(2)
            params = {"pagetoken": next_token, "key": API_KEY}
        except Exception as e:
            log.warning(f"Search error: {e}")
            break
    return results


def get_details(place_id):
    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": place_id,
                "fields": "formatted_phone_number,international_phone_number,website,opening_hours,user_ratings_total,geometry",
                "key": API_KEY
            },
            timeout=10
        )
        result = r.json().get("result", {})
        phone = result.get("formatted_phone_number") or result.get("international_phone_number") or ""
        website = result.get("website", "")
        hours_data = result.get("opening_hours", {})
        hours = ""
        if hours_data:
            weekday_text = hours_data.get("weekday_text", [])
            if weekday_text:
                hours = " | ".join(weekday_text[:3])
        pop_score = result.get("user_ratings_total", 0)
        location = result.get("geometry", {}).get("location", {})
        lat = location.get("lat", "")
        lng = location.get("lng", "")
        gps = f"{lat}, {lng}" if lat and lng else ""
        return phone, website, hours, pop_score, gps
    except:
        return "", "", "", 0, ""


def dedup(places):
    seen, out = set(), []
    for p in places:
        pid = p.get("place_id")
        if pid and pid not in seen:
            seen.add(pid)
            out.append(p)
    return out


def should_remove(name, addr):
    text = (str(name or "") + " " + str(addr or "")).lower()
    return any(k in text for k in REMOVE_KEYWORDS)


def get_specialty(name, addr):
    text = (str(name or "") + " " + str(addr or "")).lower()
    for keywords, spec in SPECIALTY_MAP:
        for kw in keywords:
            if kw in text:
                return spec
    return "GP"


def get_tier(rating, pop_score):
    if rating >= 4.5 and pop_score >= 100:
        return "High"
    elif rating >= 4.0 and pop_score >= 30:
        return "Medium"
    else:
        return "Low"


def get_area(address):
    parts = str(address or "").split(",")
    if len(parts) >= 2:
        return parts[-3].strip() if len(parts) >= 3 else parts[-2].strip()
    return ""


def is_mobile(phone):
    p = str(phone or "").strip().replace(" ", "").replace("-", "")
    return p.startswith("03") or p.startswith("+923")


def safe_float(val):
    try:
        return float(val)
    except:
        return 0.0


def collect_doctors():
    all_places = []
    for zone in FAISALABAD_ZONES:
        log.info(f"Zone: {zone['name']}")
        for query in DOCTOR_QUERIES:
            places = nearby_search(zone["lat"], zone["lng"], query)
            all_places.extend(places)
            log.info(f"  {query}: {len(places)} results")
            time.sleep(0.5)
    all_places = dedup(all_places)
    log.info(f"Unique places: {len(all_places)}")

    results = []
    total = len(all_places)
    for i, place in enumerate(all_places):
        name = place.get("name", "")
        address = place.get("vicinity", "") or place.get("formatted_address", "")

        if should_remove(name, address):
            continue

        pid = place.get("place_id", "")
        rating = safe_float(place.get("rating", 0))
        specialty = get_specialty(name, address)
        area = get_area(address)

        phone, website, hours, pop_score, gps = get_details(pid) if pid else ("", "", "", 0, "")
        time.sleep(0.3)

        tier = get_tier(rating, pop_score)
        mobile = is_mobile(phone)

        results.append({
            "name":       name,
            "specialty":  specialty,
            "phone":      phone,
            "mobile":     mobile,
            "address":    address,
            "area":       area,
            "rating":     rating,
            "pop_score":  pop_score,
            "tier":       tier,
            "hours":      hours,
            "website":    website,
            "gps":        gps,
        })

        if (i + 1) % 20 == 0:
            log.info(f"Processed {i+1}/{total}")

    results.sort(key=lambda x: (0 if x["mobile"] else 1, -x["rating"], -x["pop_score"]))
    log.info(f"Final doctors: {len(results)}")
    return results


BORDER = Border(
    left=Side(style="thin", color="C8D8EE"),
    right=Side(style="thin", color="C8D8EE"),
    top=Side(style="thin", color="C8D8EE"),
    bottom=Side(style="thin", color="C8D8EE"),
)


def make_cover(ws, total_full):
    for row in range(1, 14):
        for col in range(1, 9):
            ws.cell(row=row, column=col).fill = PatternFill("solid", start_color="1B3A6B")
    ws.column_dimensions["A"].width = 70
    ws.row_dimensions[2].height = 55
    ws.row_dimensions[3].height = 30
    ws.row_dimensions[4].height = 20

    ws.merge_cells("A2:H2")
    c = ws.cell(row=2, column=1, value="Faisalabad Doctor Leads")
    c.font = Font(bold=True, name="Calibri", size=30, color="FFFFFF")
    c.alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells("A3:H3")
    c = ws.cell(row=3, column=1, value="Verified Medical Leads — Faisalabad, Punjab, Pakistan")
    c.font = Font(name="Calibri", size=14, color="8aadd4")
    c.alignment = Alignment(horizontal="center", vertical="center")

    stats = [
        f"📍  City: Faisalabad, Punjab, Pakistan",
        f"🩺  Full Database: {total_full} Verified Doctors",
        f"📋  Sample Sheet: Top 50 Leads (Mobile Numbers, Highest Rated)",
        f"⭐  Includes: Rating, Popularity Score, Tier, Specialty, Opening Hours, GPS",
        f"🗂️  Specialties: GP, ENT, Dentist, Dermatologist, Pediatrician, Cardiologist & more",
        f"🔄  Data refreshed monthly",
    ]
    for i, stat in enumerate(stats, 5):
        ws.merge_cells(f"A{i}:H{i}")
        c = ws.cell(row=i, column=1, value=stat)
        c.font = Font(name="Calibri", size=12, color="FFFFFF")
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[i].height = 24

    ws.merge_cells("A12:H12")
    c = ws.cell(row=12, column=1, value="⚠️  Sample Only — Full database & all Punjab cities available on monthly subscription")
    c.font = Font(name="Calibri", size=11, color="FFD700", italic=True, bold=True)
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[12].height = 30


def write_data_sheet(ws, rows, sheet_title):
    headers = ["#", "Doctor / Clinic", "Specialty", "Phone", "Area", "Address",
               "Rating", "Popularity Score", "Tier", "Opening Hours", "Website", "GPS"]
    widths  = [5, 32, 18, 16, 18, 42, 8, 16, 10, 40, 25, 22]

    ws.merge_cells(f"A1:{get_column_letter(len(headers))}1")
    c = ws.cell(row=1, column=1, value=sheet_title)
    c.font = Font(bold=True, name="Calibri", size=13, color="1B3A6B")
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 26

    fill = PatternFill("solid", start_color="1B3A6B")
    font = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
    for ci, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=2, column=ci, value=h)
        c.font = font; c.fill = fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BORDER
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.row_dimensions[2].height = 22

    alt = PatternFill("solid", start_color="EDF4FF")
    tier_colors = {"High": "C6EFCE", "Medium": "FFEB9C", "Low": "FFC7CE"}

    for ri, row in enumerate(rows, 3):
        rfill = alt if ri % 2 == 0 else PatternFill()
        vals = [
            ri - 2, row["name"], row["specialty"], row["phone"],
            row["area"], row["address"], row["rating"] or "",
            row["pop_score"] or "", row["tier"],
            row["hours"], row["website"], row["gps"]
        ]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v)
            c.font = Font(name="Calibri", size=10)
            c.fill = rfill
            c.alignment = Alignment(vertical="center", wrap_text=True)
            c.border = BORDER
        tier_col = 9
        tier_val = row["tier"]
        if tier_val in tier_colors:
            ws.cell(row=ri, column=tier_col).fill = PatternFill("solid", start_color=tier_colors[tier_val])
            ws.cell(row=ri, column=tier_col).font = Font(name="Calibri", size=10, bold=True)
        ws.row_dimensions[ri].height = 18

    ws.freeze_panes = "A3"


def make_excel(doctors):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    top50 = [d for d in doctors if d["mobile"]][:50]

    ws_cover = wb.create_sheet("About This Data")
    make_cover(ws_cover, len(doctors))

    ws_sample = wb.create_sheet("Top 50 Sample")
    write_data_sheet(ws_sample, top50,
        f"Faisalabad Doctors — Top 50 Sample  |  Mobile Numbers  |  Sorted by Rating")

    ws_full = wb.create_sheet("Full Doctor List")
    write_data_sheet(ws_full, doctors,
        f"Faisalabad Doctors — Full List  |  Total: {len(doctors)}")

    path = os.path.join(OUTPUT_DIR, f"{CITY}_Doctors.xlsx")
    wb.save(path)
    log.info(f"Saved: {path}")


def main():
    if not API_KEY:
        log.error("GOOGLE_API_KEY not set!")
        exit(1)
    log.info(f"Starting enriched doctor scrape for {CITY}")
    doctors = collect_doctors()
    make_excel(doctors)
    log.info("All done!")


if __name__ == "__main__":
    main()
