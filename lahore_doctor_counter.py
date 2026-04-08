import requests
import time
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

API_KEY = os.environ.get("GOOGLE_API_KEY", "")

LAHORE_ZONES = [
    {"name": "Gulberg",           "lat": 31.5120, "lng": 74.3351},
    {"name": "DHA Phase 1-2",     "lat": 31.4811, "lng": 74.4013},
    {"name": "DHA Phase 4-5",     "lat": 31.4697, "lng": 74.4197},
    {"name": "Johar Town",        "lat": 31.4697, "lng": 74.2728},
    {"name": "Model Town",        "lat": 31.4834, "lng": 74.3274},
    {"name": "Bahria Town",       "lat": 31.3656, "lng": 74.1847},
    {"name": "Wapda Town",        "lat": 31.4418, "lng": 74.2623},
    {"name": "Iqbal Town",        "lat": 31.4976, "lng": 74.2972},
    {"name": "Garden Town",       "lat": 31.5028, "lng": 74.3238},
    {"name": "Ferozepur Road",    "lat": 31.4729, "lng": 74.3054},
    {"name": "Township",          "lat": 31.4594, "lng": 74.2805},
    {"name": "Shahdara",          "lat": 31.6185, "lng": 74.3156},
    {"name": "Raiwind Road",      "lat": 31.4197, "lng": 74.3264},
    {"name": "Anarkali",          "lat": 31.5653, "lng": 74.3144},
    {"name": "Ichra",             "lat": 31.5231, "lng": 74.2967},
    {"name": "Samanabad",         "lat": 31.5389, "lng": 74.2897},
    {"name": "Allama Iqbal Town", "lat": 31.5028, "lng": 74.2728},
    {"name": "Cavalry Ground",    "lat": 31.5384, "lng": 74.3712},
    {"name": "Cantt",             "lat": 31.5497, "lng": 74.3587},
    {"name": "Mall Road",         "lat": 31.5204, "lng": 74.3587},
]

DOCTOR_QUERIES = ["doctor", "clinic", "hospital", "specialist", "medical center"]
RADIUS = 1500


def count_nearby(lat, lng, keyword):
    count = 0
    place_ids = set()
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
                return 0
            if status not in ("OK", "ZERO_RESULTS"):
                break
            for place in data.get("results", []):
                pid = place.get("place_id")
                if pid:
                    place_ids.add(pid)
            next_token = data.get("next_page_token")
            if not next_token:
                break
            time.sleep(2)
            params = {"pagetoken": next_token, "key": API_KEY}
        except Exception as e:
            log.warning(f"Error: {e}")
            break
    return len(place_ids)


def main():
    if not API_KEY:
        log.error("GOOGLE_API_KEY not set!")
        exit(1)

    log.info("Starting Lahore doctor COUNT — no detail calls, minimal cost")
    log.info(f"Zones: {len(LAHORE_ZONES)} | Queries: {len(DOCTOR_QUERIES)}")
    log.info("Estimated API cost: < $1\n")

    all_place_ids = set()
    zone_results = []

    for zone in LAHORE_ZONES:
        zone_count = 0
        zone_ids = set()
        log.info(f"Zone: {zone['name']}")

        for query in DOCTOR_QUERIES:
            url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
            params = {
                "location": f"{zone['lat']},{zone['lng']}",
                "radius": RADIUS,
                "keyword": query,
                "key": API_KEY
            }
            for _ in range(3):
                try:
                    r = requests.get(url, params=params, timeout=15)
                    data = r.json()
                    status = data.get("status")
                    if status not in ("OK", "ZERO_RESULTS"):
                        break
                    for place in data.get("results", []):
                        pid = place.get("place_id")
                        if pid:
                            zone_ids.add(pid)
                            all_place_ids.add(pid)
                    next_token = data.get("next_page_token")
                    if not next_token:
                        break
                    time.sleep(2)
                    params = {"pagetoken": next_token, "key": API_KEY}
                except Exception as e:
                    log.warning(f"Error: {e}")
                    break
            time.sleep(0.5)

        zone_count = len(zone_ids)
        zone_results.append((zone['name'], zone_count))
        log.info(f"  → {zone_count} unique listings\n")
        time.sleep(0.5)

    total = len(all_place_ids)

    log.info("=" * 50)
    log.info("LAHORE DOCTOR COUNT RESULTS")
    log.info("=" * 50)
    for zone_name, count in zone_results:
        log.info(f"  {zone_name:<25} {count} listings")
    log.info("=" * 50)
    log.info(f"  TOTAL UNIQUE DOCTORS:    {total}")
    log.info(f"  Est. after filtering:    {int(total * 0.85)} (removing non-medical)")
    log.info(f"  Est. with mobile nos:    {int(total * 0.85 * 0.86)}")
    log.info("=" * 50)
    log.info(f"\nAPI cost for this count: ~${len(LAHORE_ZONES) * len(DOCTOR_QUERIES) * 0.0032:.2f}")
    log.info(f"API cost for full scrape: ~${total * 0.017:.2f} = PKR {int(total * 0.017 * 280):,}")


if __name__ == "__main__":
    main()
