#!/usr/bin/env python3
"""
PDF TEST — Swiss Medtech Day company list.

This is a real PDF file, not a webpage, so it needs a different kind of
tool to look inside it and pull out text, not HTML parsing. This script
downloads the file and tries to read the company names out of it.
"""
import requests
import pdfplumber
import io

HEADERS = {"User-Agent": "Mozilla/5.0 (research; leadflow-ch-pdf/1.0)"}
URL = "https://www.swiss-medtech.ch/sites/default/files/2026-06/SMD26_Companies_260610.pdf"

def main():
    print(f"Downloading {URL} ...")
    r = requests.get(URL, headers=HEADERS, timeout=30)
    print(f"HTTP status: {r.status_code}, size: {len(r.content)} bytes")

    if r.status_code != 200:
        print("FAILED to download the file.")
        return

    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        print(f"Number of pages: {len(pdf.pages)}")
        first_page = pdf.pages[0]
        text = first_page.extract_text()
        print("\n--- First page raw text (first 2000 characters) ---")
        print(text[:2000] if text else "NO TEXT FOUND ON THIS PAGE")

        # Try extracting a table structure too, PDFs like this are often
        # laid out as a table (company name, booth number, category, etc.)
        tables = first_page.extract_tables()
        print(f"\n--- Tables found on first page: {len(tables)} ---")
        if tables:
            print("First 10 rows of first table:")
            for row in tables[0][:10]:
                print(row)

if __name__ == "__main__":
    main()
