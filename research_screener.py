import requests
from bs4 import BeautifulSoup
import pandas as pd
import io

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def inspect_screener(slug):
    url = f"https://www.screener.in/company/{slug}/"
    r = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(r.text, "lxml")
    
    print(f"--- Sections for {slug} ---")
    sections = [s['id'] for s in soup.find_all('section', id=True)]
    print(sections)
    
    # Check Shareholding Pattern
    shp = soup.find('section', id='shareholding')
    if shp:
        print("\n--- Shareholding Table ---")
        tables = pd.read_html(io.StringIO(str(shp.find('table'))))
        if tables:
            print(tables[0].to_string())
            
    # Check Documents (Annual Reports/Presentations)
    docs = soup.find('section', id='documents')
    if docs:
        print("\n--- Documents ---")
        for a in docs.find_all('a', href=True):
            print(f" {a.get_text(strip=True)}: {a['href']}")

inspect_screener("RELIANCE")
