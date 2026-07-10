#!/usr/bin/env python3
"""
US Financial Advisors — Contact Enrichment (FREE, SEC brochure + domain guess)
Pulls phone/email from: (A) SEC Form ADV brochure PDF, (B) guessed firm domain.
No search engine. Input: us_advisors_<STATE>.csv  Output: _enriched.csv
"""
import csv, re, time, io
from pathlib import Path
import requests
from bs4 import BeautifulSoup

STATE = "WY"
IN = Path(f"us_advisors_{STATE}.csv")
OUT = Path(f"us_advisors_{STATE}_enriched.csv")
HEADERS = {"User-Agent":"Mozilla/5.0 (research; advisor-enrich/3.0)"}
TIMEOUT = 20

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
JUNK = ("example.com","sentry","wix","godaddy","squarespace","domain.com","email.com",
        "yourdomain",".png",".jpg",".gif","webmaster@","cloudflare","schema.org","w3.org","sec.gov")

DETAIL = "https://api.adviserinfo.sec.gov/search/firm/{crd}"
CONTACT_PATHS = ["","/contact","/contact-us","/about","/team"]

def clean_emails(t):
    out=[]
    for e in EMAIL_RE.findall(t or ""):
        el=e.lower().rstrip(".")
        if not any(j in el for j in JUNK) and el not in out: out.append(el)
    return out[:3]

def clean_phones(t):
    out=[]
    for p in PHONE_RE.findall(t or ""):
        if len(re.sub(r"\D","",p)) in (10,11) and p.strip() not in out: out.append(p.strip())
    return out[:2]

def fetch(url, binary=False):
    try:
        r=requests.get(url,headers=HEADERS,timeout=TIMEOUT)
        if r.status_code==200: return r.content if binary else r.text
    except: pass
    return None

def get_brochure_url(crd):
    """Pull the brochure PDF url + address from SEC firm detail JSON."""
    data=fetch(DETAIL.format(crd=crd))
    if not data: return None
    try:
        import json
        d=json.loads(data)
        src=d
        if isinstance(d,dict) and "hits" in d:
            hits=d["hits"].get("hits",[])
            src=hits[0].get("_source",{}) if hits else {}
        # find brochure/CRS url anywhere in the record
        blob=json.dumps(src)
        m=re.search(r'https://[^"]*[Bb]rochure[^"]*', blob) or re.search(r'https://reports\.adviserinfo\.sec\.gov/crs/[^"]*\.pdf', blob)
        return m.group(0) if m else None
    except: return None

def parse_pdf(pdf_bytes):
    try:
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(pdf_bytes))
        text=" ".join((pg.extract_text() or "") for pg in reader.pages[:3])
        return clean_emails(text), clean_phones(text)
    except Exception:
        return [], []

def guess_domains(name):
    n=re.sub(r",?\s*(llc|l\.l\.c\.|l\.p\.|lp|inc\.?|ltd)\b","",name.lower())
    n=re.sub(r"[^a-z0-9 ]","",n).strip(); w=n.split()
    c=[]
    if n.replace(" ",""): c.append(n.replace(" ","")+".com")
    if len(w)>=2: c.append("".join(w[:2])+".com")
    if len(w)>=3: c.append("".join(w[:3])+".com")
    s,o=set(),[]
    for x in c:
        if x not in s and len(x)>5: s.add(x); o.append(x)
    return o[:3]

def scrape_site(base):
    if not base.startswith("http"): base="https://"+base
    em,ph=[],[]
    for p in CONTACT_PATHS:
        html=fetch(base.rstrip("/")+p)
        if not html: continue
        soup=BeautifulSoup(html,"html.parser")
        for a in soup.find_all("a",href=True):
            h=a["href"].lower()
            if h.startswith("mailto:"):
                e=h.split(":",1)[1].split("?")[0].strip()
                if e and not any(j in e for j in JUNK) and e not in em: em.append(e)
            if h.startswith("tel:"):
                t=a["href"].split(":",1)[1].strip()
                if t and t not in ph: ph.append(t)
        txt=soup.get_text(" ",strip=True)
        em+=[e for e in clean_emails(txt) if e not in em]
        ph+=[x for x in clean_phones(txt) if x not in ph]
        if em and ph: break
        time.sleep(0.2)
    return em[:3],ph[:2]

def enrich(firm):
    firm["email"]=""; firm["phone"]=""; firm["website"]=firm.get("website","")
    em,ph=[],[]
    # A: brochure PDF
    burl=get_brochure_url(firm.get("firm_crd",""))
    if burl and burl.lower().endswith(".pdf"):
        pdf=fetch(burl,binary=True)
        if pdf: em,ph=parse_pdf(pdf)
    # B: guessed domain (if still missing)
    if not em or not ph:
        for dom in guess_domains(firm.get("firm","")):
            html=fetch("https://"+dom)
            if html and len(html)>500:
                low=html.lower(); fw=firm.get("firm","").lower().split()[0] if firm.get("firm") else ""
                if fw and (fw in low or "advisor" in low or "wealth" in low or "invest" in low):
                    firm["website"]="https://"+dom
                    se,sp=scrape_site("https://"+dom)
                    em=em or se; ph=ph or sp
                    break
            time.sleep(0.2)
    firm["email"]="; ".join(em); firm["phone"]="; ".join(ph)
    return firm

def main():
    if not IN.exists():
        print(f"[!] {IN} not found — run advisors_fetch.py first."); return
    rows=list(csv.DictReader(open(IN,encoding="utf-8")))
    # TEST MODE: set to 5 for a quick test, or len(rows) for all
    LIMIT=5
    rows=rows[:LIMIT]
    print(f"Enriching {len(rows)} firms (brochure PDF + domain guess, free)...\n")
    out=[]
    for i,f in enumerate(rows,1):
        try: r=enrich(f)
        except Exception as e: r=f; r["email"]=r.get("email",""); r["phone"]=r.get("phone","")
        tag=[k for k in ("email","phone") if r.get(k)]
        print(f"[{i}/{len(rows)}] {r['firm'][:34]:34} {('OK '+ '+'.join(tag)) if tag else '- none'}"
              + (f"  {r.get('email','')} {r.get('phone','')}" if tag else ""))
        out.append(r); time.sleep(0.3)
    fields=["firm","firm_crd","city","state","website","email","phone"]
    with open(OUT,"w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(out)
    n=len(out) or 1
    we=sum(1 for r in out if r.get("email")); wp=sum(1 for r in out if r.get("phone"))
    wa=sum(1 for r in out if r.get("email") or r.get("phone"))
    print(f"\n=== COVERAGE ({STATE}, {len(out)} firms) ===")
    print(f"  email:{we} ({100*we//n}%)  phone:{wp} ({100*wp//n}%)  any:{wa} ({100*wa//n}%)")
    print(f"  -> {OUT}")

if __name__=="__main__":
    main()
