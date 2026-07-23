#!/usr/bin/env python3
"""
QUICK CHECK — does the startup.ch login actually work?

Run this BEFORE the full discover_ch.py run. Only checks one page,
takes a few seconds, tells you plainly whether the saved login session
is working or has expired.
"""
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (research; leadflow-ch-logincheck/1.0)"}

STARTUP_CH_COOKIES = {
    "CFID": "13020119",
    "CFTOKEN": "a3fba30caae58ee0-658476CC-A96C-B0CB-42DACABE50AFAC77",
}

def main():
    url = "https://www.startup.ch/medtech-startups"
    print(f"Checking startup.ch login using saved session...")
    try:
        r = requests.get(url, headers=HEADERS, cookies=STARTUP_CH_COOKIES, timeout=20)
    except Exception as e:
        print(f"FAILED — could not reach the site at all: {e}")
        return

    print(f"HTTP status: {r.status_code}")

    if r.status_code == 403:
        print("RESULT: BLOCKED. The login session has likely expired.")
        print("Fix: log into startup.ch again in a browser, grab fresh CFID/CFTOKEN")
        print("values the same way as before, and update both scripts.")
        return

    if r.status_code != 200:
        print(f"RESULT: unexpected response ({r.status_code}). Something else is wrong.")
        return

    if "just a moment" in r.text.lower()[:2000]:
        print("RESULT: got a 200 response, but the page is still a bot-check screen.")
        print("The login session is not working. Fix: refresh the cookie values.")
        return

    # If we get here, real content should be present
    if "medtech" in r.text.lower() or "startup" in r.text.lower():
        print("RESULT: SUCCESS. Login is working, real page content came through.")
        print("Safe to proceed with the full discover_ch.py run.")
    else:
        print("RESULT: unclear. Got a 200 and it's not a bot-check page, but the")
        print("content doesn't look like the expected startup listing either.")
        print("Worth a manual look before running the full collection.")

if __name__ == "__main__":
    main()
