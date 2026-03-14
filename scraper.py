"""
Punjab Medical Leads Scraper
Scrapes Doctors + Medical Stores for all major Punjab cities.
Outputs one Excel file per city with two sheets: Doctors & Medical Stores.
"""

import requests
from bs4 import BeautifulSoup
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import time, random, os, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PUNJAB_CITIES = [
    "Lahore", "Faisalabad", "Rawalpindi", "Gujranwala", "Multan",
    "Bahawalpur", "Sargodha", "Sialkot", "Sheikhupura", "Rahim Yar Khan",
    "Jhang", "Gujrat", "Sahiwal", "Okara", "Kasur",
    "Dera Ghazi Khan", "Muzaffargarh", "Chiniot", "Hafizabad", "Mandi Bahauddin"
]

AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
]

OUTPUT_DIR = "output"

# ── HELPERS ────────────────────────────────────────────────────────────────────

def headers():
    return {
        "User-Agent": random.choice(AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
    }

def fetch(url):
    for _ in range(3):
        try:
            r = requests.get(url, headers=headers(), timeout=14)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            if r.status_code == 429:
                time.sleep(12)
        except Exception as e:
            log.warning(f"Fetch error: {e}")
        time.sleep(random.uniform(2, 4))
    return None

def txt(el):
    return el.get_text(strip=True) if el else ""

def slug(city):
    return city.lower().replace(" ", "-")

def dedup(items, key_fn):
    seen, out = set(), []
    for item in items:
        k = key_fn(item)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out

# ── DOCTOR SCRAPERS ────────────────────────────────────────────────────────────

def doctors_marham(city):
    results = []
    for page in range(1, 8):
        url = f"https://www.marham.pk/doctors/pakistan/{slug(city)}" + (f"?page={page}" if page > 1 else "")
        soup = fetch(url)
        if not soup: break
        cards = soup.select("div.doctor-card, div[class*='doctor-info'], div[class*='DoctorCard']")
        if not cards: break
        for c in cards:
            name  = txt(c.select_one("h2,h3,.doc-name,a[class*='name']"))
            spec  = txt(c.select_one(".speciality,.specialty,span[class*='spec']"))
            clinic= txt(c.select_one(".hospital-name,.clinic-name,span[class*='hospital']"))
            addr  = txt(c.select_one(".address,span[class*='address'],.location"))
            ph_el = c.select_one("a[href^='tel:']")
            phone = ph_el["href"].replace("tel:","").strip() if ph_el else ""
            if name and len(name) > 2:
                results.append({"Name": name, "Specialty": spec, "Clinic": clinic,
                                 "Phone": phone, "Address": addr, "Source": "Marham.pk"})
        time.sleep(random.uniform(1.5, 3))
        if not soup.select_one("a[rel='next'],a.next,li.next a"): break
    return results

def doctors_oladoc(city):
    results = []
    for page in range(1, 8):
        url = f"https://oladoc.com/pakistan/{slug(city)}/doctors" + (f"?page={page}" if page > 1 else "")
        soup = fetch(url)
        if not soup: break
        cards = soup.select("div.doctor-card,div[class*='DoctorCard'],li[class*='doctor']")
        if not cards: break
        for c in cards:
            name  = txt(c.select_one("h2,h3,h4,.doctor-name"))
            spec  = txt(c.select_one(".speciality,.specialization,span[class*='spec']"))
            clinic= txt(c.select_one(".clinic,.hospital,span[class*='clinic']"))
            addr  = txt(c.select_one(".address,.location,span[class*='loc']"))
            ph_el = c.select_one("a[href^='tel:']")
            phone = ph_el["href"].replace("tel:","").strip() if ph_el else ""
            if name and len(name) > 2:
                results.append({"Name": name, "Specialty": spec, "Clinic": clinic,
                                 "Phone": phone, "Address": addr, "Source": "Oladoc.com"})
        time.sleep(random.uniform(1.5, 3))
        if not soup.select_one("a[rel='next'],a.next"): break
    return results

def doctors_sehat(city):
    results = []
    for page in range(1, 5):
        url = f"https://www.sehat.com.pk/doctors/{slug(city)}" + (f"?page={page}" if page > 1 else "")
        soup = fetch(url)
        if not soup: break
        cards = soup.select("div.doctor-listing,div[class*='doctor'],li[class*='doctor']")
        if not cards: break
        for c in cards:
            name = txt(c.select_one("h2,h3,.name"))
            spec = txt(c.select_one(".specialty,.spec,small"))
            addr = txt(c.select_one(".address,.location"))
            if name and len(name) > 2:
                results.append({"Name": name, "Specialty": spec, "Clinic": "",
                                 "Phone": "", "Address": addr, "Source": "Sehat.com.pk"})
        time.sleep(random.uniform(1.5, 2.5))
        if not soup.select_one("a[rel='next'],a.next"): break
    return results

def get_doctors(city):
    log.info(f"  [Doctors] Marham...")
    d = doctors_marham(city)
    log.info(f"  [Doctors] Oladoc...")
    d += doctors_oladoc(city)
    log.info(f"  [Doctors] Sehat...")
    d += doctors_sehat(city)
    d = dedup(d, lambda x: (x["Name"].lower().strip(), city.lower()))
    log.info(f"  [Doctors] {len(d)} unique")
    return d

# ── MEDICAL STORE SCRAPERS ─────────────────────────────────────────────────────

def stores_google_places(city):
    """
    Uses Google Places Text Search API.
    Set GOOGLE_API_KEY env variable in GitHub Actions secrets to enable.
    """
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        log.info("  [Stores] No GOOGLE_API_KEY set, skipping Google Places.")
        return []

    results = []
    queries = [f"medical store {city} Pakistan", f"pharmacy {city} Pakistan", f"dawakhana {city} Pakistan"]

    for query in queries:
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        params = {"query": query, "key": api_key}
        next_token = None

        for _ in range(3):  # up to 3 pages = 60 results per query
            if next_token:
                params = {"pagetoken": next_token, "key": api_key}
                time.sleep(2)
            try:
                r = requests.get(url, params=params, timeout=12)
                data = r.json()
                for place in data.get("results", []):
                    name    = place.get("name", "")
                    address = place.get("formatted_address", "")
                    phone   = ""
                    # Get phone via Place Details
                    pid = place.get("place_id", "")
                    if pid:
                        det = requests.get(
                            "https://maps.googleapis.com/maps/api/place/details/json",
                            params={"place_id": pid, "fields": "formatted_phone_number", "key": api_key},
                            timeout=10
                        ).json()
                        phone = det.get("result", {}).get("formatted_phone_number", "")
                        time.sleep(0.3)
                    results.append({"Name": name, "Type": "Medical Store/Pharmacy",
                                    "Phone": phone, "Address": address, "Source": "Google Places"})
                next_token = data.get("next_page_token")
                if not next_token: break
            except Exception as e:
                log.warning(f"Google Places error: {e}")
                break
        time.sleep(random.uniform(1, 2))

    return results

def stores_marham(city):
    """Scrape pharmacies listed on Marham."""
    results = []
    for page in range(1, 5):
        url = f"https://www.marham.pk/pharmacy/{slug(city)}" + (f"?page={page}" if page > 1 else "")
        soup = fetch(url)
        if not soup: break
        cards = soup.select("div[class*='pharmacy'], div[class*='store'], div[class*='med-store']")
        if not cards: break
        for c in cards:
            name  = txt(c.select_one("h2,h3,.name,a"))
            addr  = txt(c.select_one(".address,.location"))
            ph_el = c.select_one("a[href^='tel:']")
            phone = ph_el["href"].replace("tel:","").strip() if ph_el else ""
            if name and len(name) > 2:
                results.append({"Name": name, "Type": "Medical Store/Pharmacy",
                                 "Phone": phone, "Address": addr, "Source": "Marham.pk"})
        time.sleep(random.uniform(1.5, 2.5))
        if not soup.select_one("a[rel='next'],a.next"): break
    return results

def stores_osmscrape(city):
    """
    OpenStreetMap Overpass API — completely free, no key needed.
    Finds pharmacies tagged on the map.
    """
    results = []
    query = f"""
    [out:json][timeout:30];
    area["name"="{city}"]["admin_level"~"6|7|8"]->.a;
    (
      node["amenity"="pharmacy"](area.a);
      node["shop"="chemist"](area.a);
      node["amenity"="medical_store"](area.a);
    );
    out body;
    """
    try:
        r = requests.post("https://overpass-api.de/api/interpreter",
                          data={"data": query}, timeout=30, headers={"User-Agent": random.choice(AGENTS)})
        data = r.json()
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            name  = tags.get("name") or tags.get("name:en") or tags.get("name:ur") or ""
            phone = tags.get("phone") or tags.get("contact:phone") or ""
            addr  = ", ".join(filter(None, [
                tags.get("addr:housenumber",""),
                tags.get("addr:street",""),
                tags.get("addr:city",""),
            ]))
            if name:
                results.append({"Name": name, "Type": "Medical Store/Pharmacy",
                                 "Phone": phone, "Address": addr or city, "Source": "OpenStreetMap"})
        log.info(f"  [Stores] OpenStreetMap: {len(results)} found")
    except Exception as e:
        log.warning(f"OSM error: {e}")
    return results

def get_stores(city):
    log.info(f"  [Stores] OpenStreetMap...")
    s = stores_osmscrape(city)
    log.info(f"  [Stores] Marham pharmacies...")
    s += stores_marham(city)
    log.info(f"  [Stores] Google Places...")
    s += stores_google_places(city)
    s = dedup(s, lambda x: (x["Name"].lower().strip(), city.lower()))
    log.info(f"  [Stores] {len(s)} unique")
    return s

# ── EXCEL EXPORT ───────────────────────────────────────────────────────────────

def make_excel(city, doctors, stores):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    _write_doctors_sheet(wb.create_sheet("🩺 Doctors"), doctors, city)
    _write_stores_sheet(wb.create_sheet("💊 Medical Stores"), stores, city)

    path = os.path.join(OUTPUT_DIR, f"{city}.xlsx")
    wb.save(path)
    log.info(f"  Saved: {path}  ({len(doctors)} doctors, {len(stores)} stores)")

BORDER = Border(
    left=Side(style="thin", color="C8D8EE"),
    right=Side(style="thin", color="C8D8EE"),
    top=Side(style="thin", color="C8D8EE"),
    bottom=Side(style="thin", color="C8D8EE"),
)

def _header_row(ws, headers, col_widths, fill_color):
    fill = PatternFill("solid", start_color=fill_color)
    font = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
    for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
        c = ws.cell(row=2, column=ci, value=h)
        c.font = font; c.fill = fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BORDER
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.row_dimensions[2].height = 22

def _title_row(ws, label, total, ncols):
    ws.insert_rows(1)
    c = ws.cell(row=1, column=1, value=f"{label}  |  Total: {total}")
    c.font = Font(bold=True, name="Calibri", size=13, color="1B3A6B")
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    ws.row_dimensions[1].height = 26

def _data_rows(ws, rows, vals_fn, start_row=3):
    alt = PatternFill("solid", start_color="EDF4FF")
    for ri, row in enumerate(rows, start_row):
        fill = alt if ri % 2 == 0 else PatternFill()
        for ci, v in enumerate(vals_fn(row), 1):
            c = ws.cell(row=ri, column=ci, value=v)
            c.font = Font(name="Calibri", size=10)
            c.fill = fill
            c.alignment = Alignment(vertical="center", wrap_text=True)
            c.border = BORDER
        ws.row_dimensions[ri].height = 18
    ws.freeze_panes = "A3"

def _write_doctors_sheet(ws, doctors, city):
    cols    = ["#", "Doctor Name", "Specialty", "Clinic / Hospital", "Phone", "Address", "Source"]
    widths  = [5, 28, 22, 28, 18, 35, 14]
    _header_row(ws, cols, widths, "1B3A6B")
    _data_rows(ws, doctors, lambda d: [
        doctors.index(d)+1, d["Name"], d["Specialty"], d["Clinic"], d["Phone"], d["Address"], d["Source"]
    ])
    _title_row(ws, f"{city} — Doctors", len(doctors), len(cols))

def _write_stores_sheet(ws, stores, city):
    cols    = ["#", "Store Name", "Type", "Phone", "Address", "Source"]
    widths  = [5, 30, 22, 18, 40, 16]
    _header_row(ws, cols, widths, "1A5C3A")
    _data_rows(ws, stores, lambda s: [
        stores.index(s)+1, s["Name"], s["Type"], s["Phone"], s["Address"], s["Source"]
    ])
    _title_row(ws, f"{city} — Medical Stores & Pharmacies", len(stores), len(cols))

# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    city_filter = os.environ.get("CITY", "").strip()
    cities = [c for c in PUNJAB_CITIES if c.lower() == city_filter.lower()] if city_filter else PUNJAB_CITIES

    log.info(f"Starting scrape for {len(cities)} cities")

    for city in cities:
        log.info(f"\n{'='*50}\n📍 {city}\n{'='*50}")
        doctors = get_doctors(city)
        stores  = get_stores(city)
        make_excel(city, doctors, stores)

    log.info(f"\n✅ All done. Files saved in /{OUTPUT_DIR}/")

if __name__ == "__main__":
    main()
