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

def doctors_marham(city):
    results = []
    for page in range(1, 8):
        url = f"https://www.marham.pk/doctors/pakistan/{slug(city)}" + (f"?page={page}" if page > 1 else "")
        soup = fetch(url)
        if not soup: break
        cards = soup.select("div.doctor-card, div[class*='doctor-info'], div[class*='DoctorCard']")
        if not cards: break
        for c in cards:
            name   = txt(c.select_one("h2,h3,.doc-name,a[class*='name']"))
            spec   = txt(c.select_one(".speciality,.specialty,span[class*='spec']"))
            clinic = txt(c.select_one(".hospital-name,.clinic-name,span[class*='hospital']"))
            addr   = txt(c.select_one(".address,span[class*='address'],.location"))
            ph_el  = c.select_one("a[href^='tel:']")
            phone  = ph_el["href"].replace("tel:","").strip() if ph_el else ""
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
            name   = txt(c.select_one("h2,h3,h4,.doctor-name"))
            spec   = txt(c.select_one(".speciality,.specialization,span[class*='spec']"))
            clinic = txt(c.select_one(".clinic,.hospital,span[class*='clinic']"))
            addr   = txt(c.select_one(".address,.location,span[class*='loc']"))
            ph_el  = c.select_one("a[href^='tel:']")

