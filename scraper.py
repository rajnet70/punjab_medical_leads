import requests
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import time
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PUNJAB_CITIES = [
    "Lahore", "Faisalabad", "Rawalpindi", "Gujranwala", "Multan",
    "Bahawalpur", "Sargodha", "Sialkot", "Sheikhupura", "Rahim Yar Khan",
    "Jhang", "Gujrat", "Sahiwal", "Okara", "Kasur",
    "Dera Ghazi Khan", "Muzaffargarh", "Chiniot", "Hafizabad", "Mandi Bahauddin"
]

DOCTOR_QUERIES = [
    "doctor clinic", "physician", "specialist hospital",
    "medical center", "health clinic", "general practitioner"
]

STORE_QUERIES = [
    "medical store", "pharmacy", "dawakhana",
    "chemist shop", "drugstore"
]

OUTPUT_DIR = "output"
API_KEY = os.environ.get("GOOGLE_API_KEY", "")


def places_search(query, city):
    results = []
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": f"{query} in {city} Pakistan", "key": API_KEY}

    for _ in range(3):
        try:
            r = requests.get(url, params=params, timeout=15)
            data = r.json()

            if data.get("status") not in ("OK", "ZERO_RESULTS"):
                log.warning(f"Places API status: {data.get('status')} for {query} in {city}")
                break

            for place in data.get("results", []):
                results.append(place)

            next_token = data.get("next_page_token")
            if not next_token:
                break

            time.sleep(2)
            params = {"pagetoken": next_token, "key": API_KEY}

        except Exception as e:
            log.warning(f"Search error: {e}")
            break

    return results


def get_phone(place_id):
    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={"place_id": place_id, "fields": "formatted_phone_number", "key": API_KEY},
            timeout=10
        )
        return r.json().get("result", {}).get("formatted_phone_number", "")
    except:
        return ""


def search_doctors(city):
    log.info(f"  [Doctors] Searching Google Places for {city}...")
    all_places = []
    seen_ids = set()

    for query in DOCTOR_QUERIES:
        places = places_search(query, city)
        for p in places:
            pid = p.get("place_id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_places.append(p)
        time.sleep(1)

    log.info(f"  [Doctors] Found {len(all_places)} places, fetching phone numbers...")

    results = []
    for i, place in enumerate(all_places):
        name    = place.get("name", "")
        address = place.get("formatted_address", "")
        pid     = place.get("place_id", "")
        rating  = str(place.get("rating", ""))
        phone   = get_phone(pid) if pid else ""
        time.sleep(0.3)

        if (i + 1) % 20 == 0:
            log.info(f"  [Doctors] Processed {i+1}/{len(all_places)}...")

        results.append({
            "Name": name,
            "Specialty": "",
            "Clinic": name,
            "Phone": phone,
            "Address": address,
            "Rating": rating,
            "Source": "Google Places"
        })

    log.info(f"  [Doctors] {len(results)} doctors collected for {city}")
    return results


def search_stores(city):
    log.info(f"  [Stores] Searching Google Places for {city}...")
    all_places = []
    seen_ids = set()

    for query in STORE_QUERIES:
        places = places_search(query, city)
        for p in places:
            pid = p.get("place_id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_places.append(p)
        time.sleep(1)

    log.info(f"  [Stores] Found {len(all_places)} places, fetching phone numbers...")

    results = []
    for i, place in enumerate(all_places):
        name    = place.get("name", "")
        address = place.get("formatted_address", "")
        pid     = place.get("place_id", "")
        rating  = str(place.get("rating", ""))
        phone   = get_phone(pid) if pid else ""
        time.sleep(0.3)

        if (i + 1) % 20 == 0:
            log.info(f"  [Stores] Processed {i+1}/{len(all_places)}...")

        results.append({
            "Name": name,
            "Type": "Medical Store / Pharmacy",
            "Phone": phone,
            "Address": address,
            "Rating": rating,
            "Source": "Google Places"
        })

    log.info(f"  [Stores] {len(results)} stores collected for {city}")
    return results


BORDER = Border(
    left=Side(style="thin", color="C8D8EE"),
    right=Side(style="thin", color="C8D8EE"),
    top=Side(style="thin", color="C8D8EE"),
    bottom=Side(style="thin", color="C8D8EE"),
)


def write_title(ws, label, total, ncols):
    c = ws.cell(row=1, column=1, value=f"{label}  |  Total: {total}")
    c.font = Font(bold=True, name="Calibri", size=13, color="1B3A6B")
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    ws.row_dimensions[1].height = 26


def write_headers(ws, cols, widths, color):
    fill = PatternFill("solid", start_color=color)
    font = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
    for ci, (h, w) in enumerate(zip(cols, widths), 1):
        c = ws.cell(row=2, column=ci, value=h)
        c.font = font
        c.fill = fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BORDER
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.row_dimensions[2].height = 22


def write_data(ws, rows, vals_fn):
    alt = PatternFill("solid", start_color="EDF4FF")
    for ri, row in enumerate(rows, 3):
        fill = alt if ri % 2 == 0 else PatternFill()
        for ci, v in enumerate(vals_fn(ri - 3, row), 1):
            c = ws.cell(row=ri, column=ci, value=v)
            c.font = Font(name="Calibri", size=10)
            c.fill = fill
            c.alignment = Alignment(vertical="center", wrap_text=True)
            c.border = BORDER
        ws.row_dimensions[ri].height = 18
    ws.freeze_panes = "A3"


def make_excel(city, doctors, stores):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    ws1 = wb.create_sheet("Doctors")
    cols1   = ["#", "Name", "Phone", "Address", "Rating", "Source"]
    widths1 = [5, 32, 18, 45, 8, 14]
    write_title(ws1, f"{city} — Doctors", len(doctors), len(cols1))
    write_headers(ws1, cols1, widths1, "1B3A6B")
    write_data(ws1, doctors, lambda i, d: [
        i+1, d["Name"], d["Phone"], d["Address"], d["Rating"], d["Source"]
    ])

    ws2 = wb.create_sheet("Medical Stores")
    cols2   = ["#", "Store Name", "Type", "Phone", "Address", "Rating", "Source"]
    widths2 = [5, 32, 22, 18, 40, 8, 14]
    write_title(ws2, f"{city} — Medical Stores & Pharmacies", len(stores), len(cols2))
    write_headers(ws2, cols2, widths2, "1A5C3A")
    write_data(ws2, stores, lambda i, s: [
        i+1, s["Name"], s["Type"], s["Phone"], s["Address"], s["Rating"], s["Source"]
    ])

    path = os.path.join(OUTPUT_DIR, f"{city}.xlsx")
    wb.save(path)
    log.info(f"Saved: {path} ({len(doctors)} doctors, {len(stores)} stores)")


def main():
    if not API_KEY:
        log.error("GOOGLE_API_KEY not set! Add it as a GitHub secret.")
        exit(1)

    city_filter = os.environ.get("CITY", "").strip()
    cities = [c for c in PUNJAB_CITIES if c.lower() == city_filter.lower()] if city_filter else PUNJAB_CITIES

    log.info(f"Starting scrape for {len(cities)} cities")

    for city in cities:
        log.info(f"\n{'='*50}\nProcessing: {city}\n{'='*50}")
        doctors = search_doctors(city)
        stores  = search_stores(city)
        make_excel(city, doctors, stores)

    log.info("All done!")


if __name__ == "__main__":
            main()

    
