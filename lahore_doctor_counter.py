import requests
import time
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

API_KEY = os.environ.get("GOOGLE_API_KEY", "")

# Comprehensive Lahore zones — 40 zones covering entire city
LAHORE_ZONES = [
    # ── CENTRAL ──────────────────────────────────────────
    {"name": "Mall Road",              "lat": 31.5204, "lng": 74.3587},
    {"name": "Anarkali",               "lat": 31.5653, "lng": 74.3144},
    {"name": "Cantt",                  "lat": 31.5497, "lng": 74.3587},
    {"name": "Civil Lines",            "lat": 31.5497, "lng": 74.3280},
    {"name": "Garhi Shahu",            "lat": 31.5380, "lng": 74.3280},
    {"name": "Gulberg",                "lat": 31.5120, "lng": 74.3351},
    {"name": "Garden Town",            "lat": 31.5028, "lng": 74.3238},
    {"name": "Cavalry Ground",         "lat": 31.5384, "lng": 74.3712},
    {"name": "Shadman",                "lat": 31.5250, "lng": 74.3200},

    # ── NORTH ────────────────────────────────────────────
    {"name": "Shahdara",               "lat": 31.6185, "lng": 74.3156},
    {"name": "Shahdara Town",          "lat": 31.6350, "lng": 74.3300},
    {"name": "Harbanspura",            "lat": 31.5750, "lng": 74.2950},
    {"name": "Aziz Bhatti Town",       "lat": 31.5900, "lng": 74.3400},
    {"name": "Badami Bagh",            "lat": 31.5730, "lng": 74.3250},
    {"name": "Islampura",              "lat": 31.5600, "lng": 74.3050},

    # ── EAST ─────────────────────────────────────────────
    {"name": "DHA Phase 1-2",          "lat": 31.4811, "lng": 74.4013},
    {"name": "DHA Phase 4-5",          "lat": 31.4697, "lng": 74.4197},
    {"name": "DHA Phase 6",            "lat": 31.4550, "lng": 74.4350},
    {"name": "Bedian Road",            "lat": 31.4313, "lng": 74.4561},
    {"name": "Cavalry Ground East",    "lat": 31.5200, "lng": 74.4000},
    {"name": "Mustafa Town",           "lat": 31.5050, "lng": 74.3800},

    # ── WEST ─────────────────────────────────────────────
    {"name": "Ichra",                  "lat": 31.5231, "lng": 74.2967},
    {"name": "Samanabad",              "lat": 31.5389, "lng": 74.2897},
    {"name": "Gulshan-e-Ravi",         "lat": 31.5500, "lng": 74.2750},
    {"name": "Nawaz Town",             "lat": 31.5150, "lng": 74.2600},
    {"name": "Sabzazar",               "lat": 31.5350, "lng": 74.2500},
    {"name": "Kot Lakhpat",            "lat": 31.5000, "lng": 74.2700},

    # ── SOUTH ────────────────────────────────────────────
    {"name": "Johar Town",             "lat": 31.4697, "lng": 74.2728},
    {"name": "Model Town",             "lat": 31.4834, "lng": 74.3274},
    {"name": "Ferozepur Road",         "lat": 31.4729, "lng": 74.3054},
    {"name": "Township",               "lat": 31.4594, "lng": 74.2805},
    {"name": "Iqbal Town",             "lat": 31.4976, "lng": 74.2972},
    {"name": "Wahdat Road",            "lat": 31.4900, "lng": 74.3150},
    {"name": "Wapda Town",             "lat": 31.4418, "lng": 74.2623},
    {"name": "Multan Road",            "lat": 31.4500, "lng": 74.3100},
    {"name": "Allama Iqbal Town",      "lat": 31.5028, "lng": 74.2728},

    # ── FAR SOUTH ────────────────────────────────────────
    {"name": "Bahria Town",            "lat": 31.3656, "lng": 74.1847},
    {"name": "Lake City",              "lat": 31.4200, "lng": 74.4000},
    {"name": "Thokar Niaz Baig",       "lat": 31.4050, "lng": 74.2600},
    {"name": "Raiwind Road",           "lat": 31.3800, "lng": 74.3000},
    {"name": "Valencia Town",          "lat": 31.4600, "lng": 74.3500},
]

DOCTOR_QUERIES = ["doctor", "clinic", "hospital", "specialist", "medical center"]
RADIUS = 1500


def main():
    if not API_KEY:
        log.error("GOOGLE_API_KEY not set!")
        exit(1)

    log.info(f"Starting Lahore doctor COUNT — {len(LAHORE_ZONES)} zones")
    log.info(f"Estimated API cost: ~${len(LAHORE_ZONES) * len(DOCTOR_QUERIES) * 0.0032:.2f}\n")

    all_place_ids = set()
    zone_results = []

    for zone in LAHORE_ZONES:
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
                    if status == "REQUEST_DENIED":
                        log.error(f"API key error: {data.get('error_message')}")
                        return
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
        zone_results.append((zone["name"], zone_count))
        log.info(f"  → {zone_count} unique listings\n")

    total = len(all_place_ids)
    est_filtered = int(total * 0.85)
    est_mobile   = int(est_filtered * 0.86)
    api_cost_usd = total * 0.017
    api_cost_pkr = int(api_cost_usd * 280)

    log.info("=" * 55)
    log.info("LAHORE DOCTOR COUNT — FINAL RESULTS")
    log.info("=" * 55)
    for zone_name, count in sorted(zone_results, key=lambda x: -x[1]):
        bar = "█" * (count // 10)
        log.info(f"  {zone_name:<28} {count:>4}  {bar}")
    log.info("=" * 55)
    log.info(f"  TOTAL UNIQUE LISTINGS:     {total:,}")
    log.info(f"  Est. after filtering:      {est_filtered:,}  (removing non-medical)")
    log.info(f"  Est. with mobile numbers:  {est_mobile:,}")
    log.info("=" * 55)
    log.info(f"  API cost for this count:   ~$0.65")
    log.info(f"  API cost for full scrape:  ~${api_cost_usd:.0f} = PKR {api_cost_pkr:,}")
    log.info("=" * 55)


if __name__ == "__main__":
    main()
