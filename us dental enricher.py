import os
import re
import time
import requests
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from bs4 import BeautifulSoup

# ── CONFIG ────────────────────────────────────────────────────────────────────
CITY    = os.environ.get('CITY', 'New York')
INPUT   = f'output/{CITY}_Dental_Clinics.xlsx'
OUTPUT  = f'output/{CITY}_Dental_Clinics_Enriched.xlsx'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xhtml+xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

TIMEOUT = 10

# ── STYLES ────────────────────────────────────────────────────────────────────
BORDER = Border(
    left=Side(style='thin', color='C8D8EE'),
    right=Side(style='thin', color='C8D8EE'),
    top=Side(style='thin', color='C8D8EE'),
    bottom=Side(style='thin', color='C8D8EE'),
)
HEADER_FILL  = PatternFill('solid', start_color='1B3A6B')
SUBHEAD_FILL = PatternFill('solid', start_color='2E5FA3')
ALT_FILL     = PatternFill('solid', start_color='EDF4FF')
HIGH_FILL    = PatternFill('solid', start_color='C6EFCE')
MED_FILL     = PatternFill('solid', start_color='FFEB9C')
LOW_FILL     = PatternFill('solid', start_color='FFC7CE')
GOLD_FILL    = PatternFill('solid', start_color='FFF2CC')
ENRICH_FILL  = PatternFill('solid', start_color='1a1040')

# ── ENRICHMENT ────────────────────────────────────────────────────────────────
def fetch_website(url):
    """Fetch website content. Returns (html, error)."""
    if not url or url == 'N/A':
        return None, 'No website'
    try:
        clean = url if url.startswith('http') else f'https://{url}'
        # Strip tracking params
        clean = clean.split('?')[0].split('#')[0]
        resp = requests.get(clean, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code == 200:
            return resp.text, None
        return None, f'HTTP {resp.status_code}'
    except requests.exceptions.SSLError:
        try:
            clean = url.replace('https://', 'http://')
            resp = requests.get(clean, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            return resp.text, None
        except:
            return None, 'SSL Error'
    except requests.exceptions.Timeout:
        return None, 'Timeout'
    except Exception as e:
        return None, str(e)[:30]

def extract_signals(html, url):
    """Extract enrichment signals from website HTML."""
    if not html:
        return {
            'services':       'N/A',
            'dentist_count':  'N/A',
            'booking_online': 'N/A',
            'insurance':      'N/A',
            'years_open':     'N/A',
            'social_media':   'N/A',
            'tech_signals':   'N/A',
        }

    soup = BeautifulSoup(html, 'lxml')
    text = soup.get_text(separator=' ', strip=True).lower()
    full_html = html.lower()

    # ── SERVICES ──────────────────────────────────────────────────────────────
    service_map = {
        'General Dentistry':  ['general dentistry', 'general dental', 'family dentistry', 'routine cleaning', 'checkup', 'examination'],
        'Cosmetic':           ['cosmetic dentistry', 'teeth whitening', 'veneers', 'smile makeover', 'aesthetic dentistry'],
        'Implants':           ['dental implants', 'implant dentistry', 'tooth implant', 'implant restoration'],
        'Orthodontics':       ['orthodontics', 'braces', 'invisalign', 'clear aligners', 'teeth straightening'],
        'Periodontics':       ['periodontics', 'gum disease', 'gum treatment', 'periodontist'],
        'Endodontics':        ['root canal', 'endodontics', 'endodontist'],
        'Oral Surgery':       ['oral surgery', 'tooth extraction', 'wisdom teeth', 'oral surgeon'],
        'Pediatric':          ['pediatric dentistry', 'children dentistry', 'kids dentist', 'child dental'],
        'Emergency':          ['emergency dental', 'emergency dentist', 'same day', 'urgent dental'],
        'Prosthodontics':     ['dentures', 'crowns', 'bridges', 'prosthodontics', 'full mouth'],
    }
    found_services = [s for s, kws in service_map.items() if any(kw in text for kw in kws)]
    services = ', '.join(found_services[:4]) if found_services else 'N/A'

    # ── DENTIST COUNT ─────────────────────────────────────────────────────────
    dentist_count = 'N/A'
    patterns = [
        r'team of (\d+)\s*(dentists?|doctors?|specialists?)',
        r'(\d+)\s*(dentists?|doctors?|specialists?)\s*(on staff|on site|available)',
        r'(\d+)\+?\s*(experienced|expert|skilled|licensed)?\s*(dentists?|doctors?)',
        r'our (\d+)\s*(dentists?|providers?)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            dentist_count = f'{m.group(1)} dentists'
            break

    # ── ONLINE BOOKING ────────────────────────────────────────────────────────
    booking_signals = [
        'book online', 'book an appointment', 'schedule online', 'request appointment',
        'online booking', 'book now', 'schedule now', 'appointment request',
        'zocdoc', 'open dental', 'dentrix', 'eaglesoft'
    ]
    booking_online = 'Yes' if any(s in text for s in booking_signals) else 'N/A'

    # ── INSURANCE ─────────────────────────────────────────────────────────────
    insurance_signals = [
        'insurance', 'delta dental', 'cigna', 'metlife', 'aetna', 'guardian',
        'bluecross', 'blue cross', 'united healthcare', 'humana', 'we accept',
        'in-network', 'in network', 'insurance accepted'
    ]
    insurance = 'Accepted' if any(s in text for s in insurance_signals) else 'N/A'

    # ── YEARS OPEN ────────────────────────────────────────────────────────────
    years_open = 'N/A'
    year_patterns = [
        r'since (\d{4})',
        r'established in (\d{4})',
        r'founded in (\d{4})',
        r'serving.*since (\d{4})',
        r'open since (\d{4})',
        r'in (\d{4})\s*(?:and|,)?\s*(?:we|our)',
    ]
    for pat in year_patterns:
        m = re.search(pat, text)
        if m:
            year = int(m.group(1))
            if 1900 < year <= 2024:
                years_open = f'Since {year}'
                break

    # ── SOCIAL MEDIA ─────────────────────────────────────────────────────────
    social = []
    if 'facebook.com' in full_html: social.append('Facebook')
    if 'instagram.com' in full_html: social.append('Instagram')
    if 'twitter.com' in full_html or 'x.com' in full_html: social.append('Twitter/X')
    if 'linkedin.com' in full_html: social.append('LinkedIn')
    if 'youtube.com' in full_html: social.append('YouTube')
    if 'tiktok.com' in full_html: social.append('TikTok')
    social_media = ', '.join(social) if social else 'N/A'

    # ── TECH SIGNALS ─────────────────────────────────────────────────────────
    tech = []
    if any(s in full_html for s in ['zocdoc', 'zoc-doc']): tech.append('ZocDoc')
    if 'teledentistry' in text or 'virtual consult' in text: tech.append('Teledentistry')
    if 'patient portal' in text: tech.append('Patient Portal')
    if any(s in text for s in ['3d imaging', 'cone beam', 'cbct', 'digital xray', 'digital x-ray']): tech.append('Digital Imaging')
    if 'same day crown' in text or 'cerec' in text: tech.append('Same-Day Crowns')
    if 'laser dentistry' in text or 'laser treatment' in text: tech.append('Laser Dentistry')
    tech_signals = ', '.join(tech) if tech else 'N/A'

    return {
        'services':       services,
        'dentist_count':  dentist_count,
        'booking_online': booking_online,
        'insurance':      insurance,
        'years_open':     years_open,
        'social_media':   social_media,
        'tech_signals':   tech_signals,
    }

def enrichment_score_boost(signals):
    """Additional score points from enrichment signals."""
    boost = 0
    if signals['booking_online'] == 'Yes':        boost += 8
    if signals['insurance'] == 'Accepted':         boost += 5
    if signals['years_open'] != 'N/A':             boost += 5
    if signals['tech_signals'] != 'N/A':           boost += 5
    services = signals['services']
    if services != 'N/A':
        count = len(services.split(','))
        if count >= 4:   boost += 7
        elif count >= 2: boost += 4
    if 'Implants' in services:    boost += 5
    if 'Cosmetic' in services:    boost += 5
    if 'Orthodontics' in services: boost += 3
    return boost

def get_tier(score):
    if score >= 70: return 'High'
    if score >= 40: return 'Medium'
    return 'Low'

# ── MAIN ──────────────────────────────────────────────────────────────────────
def enrich():
    print(f'🔬 Starting enrichment for {CITY}')
    print(f'   Input: {INPUT}')

    # Load existing Excel
    wb_src = openpyxl.load_workbook(INPUT)
    ws_src = wb_src[CITY]

    # Read all rows
    headers_row = [ws_src.cell(2, c).value for c in range(1, ws_src.max_column+1)]
    print(f'   Columns: {headers_row}')

    rows = []
    for r in range(3, ws_src.max_row+1):
        row = [ws_src.cell(r, c).value for c in range(1, ws_src.max_column+1)]
        if any(row):
            rows.append(row)

    print(f'   Loaded {len(rows)} clinics')

    # Enrich each clinic
    enriched = []
    for i, row in enumerate(rows):
        name    = row[1]  # Clinic Name
        website = row[5]  # Website

        print(f'  [{i+1}/{len(rows)}] {name}')

        html, err = fetch_website(website)
        if err:
            print(f'    ⚠ {err}')

        signals = extract_signals(html, website)
        boost   = enrichment_score_boost(signals)

        # Original score is row[11], add boost capped at 100
        orig_score = int(row[11] or 0)
        new_score  = min(orig_score + boost, 100)
        new_tier   = get_tier(new_score)

        enriched.append({
            'row':     row,
            'signals': signals,
            'score':   new_score,
            'tier':    new_tier,
        })

        time.sleep(0.3)

    # ── BUILD ENRICHED EXCEL ──────────────────────────────────────────────────
    wb_out = openpyxl.Workbook()
    wb_out.remove(wb_out.active)

    high = sum(1 for e in enriched if e['tier']=='High')
    med  = sum(1 for e in enriched if e['tier']=='Medium')
    low  = sum(1 for e in enriched if e['tier']=='Low')

    # Summary tab
    ws_sum = wb_out.create_sheet('Summary', 0)
    ws_sum.sheet_view.showGridLines = False

    ws_sum.merge_cells('A1:H1')
    c = ws_sum.cell(row=1, column=1, value=f'{CITY.upper()} DENTAL CLINIC INTELLIGENCE — LEADFLOW (ENRICHED)')
    c.font = Font(bold=True, name='Calibri', size=16, color='FFFFFF')
    c.fill = HEADER_FILL
    c.alignment = Alignment(horizontal='center', vertical='center')
    ws_sum.row_dimensions[1].height = 36

    ws_sum.merge_cells('A2:H2')
    c = ws_sum.cell(row=2, column=1,
        value=f'⚠ Sample Database — {len(enriched)} Records  |  AI Enriched  |  Prepared by LeadFlow  |  June 2026  |  For Presentation Purposes Only')
    c.font = Font(bold=True, name='Calibri', size=11, color='7a5c00')
    c.fill = GOLD_FILL
    c.alignment = Alignment(horizontal='center', vertical='center')
    ws_sum.row_dimensions[2].height = 26

    ws_sum.row_dimensions[3].height = 10

    sum_headers = ['City', 'Total', 'High', 'Medium', 'Low', 'Category', 'Enrichment', 'Notes']
    sum_widths   = [16, 10, 10, 12, 10, 16, 20, 30]
    for ci, (h, w) in enumerate(zip(sum_headers, sum_widths), 1):
        c = ws_sum.cell(row=4, column=ci, value=h)
        c.font = Font(bold=True, color='FFFFFF', name='Calibri', size=11)
        c.fill = SUBHEAD_FILL
        c.alignment = Alignment(horizontal='center', vertical='center')
        c.border = BORDER
        ws_sum.column_dimensions[get_column_letter(ci)].width = w
    ws_sum.row_dimensions[4].height = 22

    # Count enrichment success
    enriched_count = sum(1 for e in enriched if e['signals']['services'] != 'N/A')
    enrich_rate = f'{int(enriched_count/len(enriched)*100)}% enriched' if enriched else 'N/A'

    vals = [CITY, len(enriched), high, med, low, 'Dental Clinics', enrich_rate, 'Sample only — full database available on request']
    for ci, v in enumerate(vals, 1):
        c = ws_sum.cell(row=5, column=ci, value=v)
        c.font = Font(name='Calibri', size=11)
        c.fill = ALT_FILL
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = BORDER
    ws_sum.row_dimensions[5].height = 22

    for ci, v in enumerate(['TOTAL', len(enriched), high, med, low, '', enrich_rate, ''], 1):
        c = ws_sum.cell(row=6, column=ci, value=v)
        c.font = Font(bold=True, color='FFFFFF', name='Calibri', size=12)
        c.fill = HEADER_FILL
        c.alignment = Alignment(horizontal='center', vertical='center')
        c.border = BORDER
    ws_sum.row_dimensions[6].height = 26

    # City tab
    ws = wb_out.create_sheet(CITY)
    ws.sheet_view.showGridLines = False

    headers = [
        '#', 'Clinic Name', 'Phone', 'Address', 'Neighbourhood',
        'Website', 'Rating', 'Reviews', 'Opening Hours',
        'GPS Latitude', 'GPS Longitude',
        # Enriched columns
        'Services *', 'Dentists *', 'Online Booking *',
        'Insurance *', 'Est. Year *', 'Social Media *', 'Tech Signals *',
        # Score
        'Score', 'Tier'
    ]
    widths = [
        5, 38, 16, 48, 20,
        30, 8, 10, 24,
        14, 14,
        50, 14, 16,
        14, 12, 36, 40,
        8, 10
    ]

    ws.merge_cells(f'A1:{get_column_letter(len(headers))}1')
    c = ws.cell(row=1, column=1,
        value=f'{CITY} — Dental Clinic Intelligence (AI Enriched)  |  {len(enriched)} Records  |  ⚠ Sample Database — LeadFlow  |  June 2026')
    c.font = Font(bold=True, name='Calibri', size=11, color='FFFFFF')
    c.fill = HEADER_FILL
    c.alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[1].height = 26

    # Enrichment note row
    ws.merge_cells(f'A2:{get_column_letter(len(headers))}2')
    c = ws.cell(row=2, column=1,
        value='* Fields marked with asterisk are AI-enriched via website analysis. N/A shown where website unavailable or data not found.')
    c.font = Font(italic=True, name='Calibri', size=9, color='c4b5fd')
    c.fill = PatternFill('solid', start_color='0d0a20')
    c.alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[2].height = 18

    for ci, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=3, column=ci, value=h)
        # Purple tint for enriched columns
        if '*' in str(h):
            c.font = Font(bold=True, color='c4b5fd', name='Calibri', size=10)
            c.fill = PatternFill('solid', start_color='1a0d35')
        else:
            c.font = Font(bold=True, color='FFFFFF', name='Calibri', size=11)
            c.fill = SUBHEAD_FILL
        c.alignment = Alignment(horizontal='center', vertical='center')
        c.border = BORDER
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.row_dimensions[3].height = 22

    for ri, e in enumerate(enriched, 4):
        row     = e['row']
        signals = e['signals']
        rfill   = ALT_FILL if ri % 2 == 0 else PatternFill()
        tier_val = e['tier']

        vals = [
            ri-3,
            row[1],   # name
            row[2],   # phone
            row[3],   # address
            row[4],   # area
            row[5],   # website
            row[6],   # rating
            row[7],   # reviews
            row[8],   # hours
            row[9],   # lat
            row[10],  # lng
            signals['services'],
            signals['dentist_count'],
            signals['booking_online'],
            signals['insurance'],
            signals['years_open'],
            signals['social_media'],
            signals['tech_signals'],
            e['score'],
            e['tier'],
        ]

        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v)
            c.font = Font(name='Calibri', size=10)
            # Purple tint for enriched columns
            if ci >= 12 and ci <= 18:
                c.fill = PatternFill('solid', start_color='0f0820') if ri % 2 == 0 else PatternFill('solid', start_color='120a25')
                c.font = Font(name='Calibri', size=10, color='FFFFFF')
            else:
                c.fill = rfill
            c.alignment = Alignment(vertical='center', wrap_text=True)
            c.border = BORDER

        # Tier colour
        tier_cell = ws.cell(row=ri, column=20)
        tier_cell.fill = HIGH_FILL if tier_val=='High' else (MED_FILL if tier_val=='Medium' else LOW_FILL)
        tier_cell.font = Font(name='Calibri', size=10, bold=True)
        ws.row_dimensions[ri].height = 30

    ws.freeze_panes = 'A4'

    wb_out.save(OUTPUT)
    print(f'\n✅ Enriched Excel saved: {OUTPUT}')
    print(f'   High: {high} | Medium: {med} | Low: {low}')
    print(f'   Enrichment rate: {enrich_rate}')

if __name__ == '__main__':
    enrich()
