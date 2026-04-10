import requests
from bs4 import BeautifulSoup
import pandas as pd
import io

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def debug_screener_all(slug):
    url = f"https://www.screener.in/company/{slug}/"
    r = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(r.text, "lxml")
    
    results = {}
    
    # 1. Shareholding
    shp_sec = soup.find('section', id='shareholding')
    if shp_sec:
        table = shp_sec.find('table')
        if table:
            df = pd.read_html(io.StringIO(str(table)))[0]
            results['shareholding'] = df.to_dict()

    # 2. Results / Growth (Compounded)
    # The growth metrics are usually in the "analysis" or a custom summary table
    # Actually they are often in a table with headers like "Compounded Sales Growth"
    growth_tables = soup.find_all('table', class_='ranges-table')
    results['growth'] = []
    for gt in growth_tables:
        df_g = pd.read_html(io.StringIO(str(gt)))[0]
        results['growth'].append(df_g.to_dict())

    # 3. Cash Flow
    cf_sec = soup.find('section', id='cash-flow')
    if cf_sec:
        table = cf_sec.find('table')
        if table:
            df = pd.read_html(io.StringIO(str(table)))[0]
            results['cash_flow'] = df.to_dict()

    # 4. Documents
    doc_sec = soup.find('section', id='documents')
    if doc_sec:
        docs = []
        for a in doc_sec.find_all('a', href=True):
            docs.append({'title': a.get_text(strip=True), 'url': a['href']})
        results['documents'] = docs

    return results

# Test with RELIANCE
import json
data = debug_screener_all("RELIANCE")
print(json.dumps(data, indent=2))
