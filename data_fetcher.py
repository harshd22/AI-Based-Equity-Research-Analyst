import yfinance as yf
import pandas as pd
import datetime
import requests
import re
import time
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta

SCREENER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def _get_screener_slug(ticker: str):
    """Convert a NSE ticker like RELIANCE.NS to its screener.in slug like RELIANCE."""
    base = ticker.replace(".NS", "").replace(".BO", "").upper()
    try:
        r = requests.get(
            f"https://www.screener.in/api/company/search/?q={base}&v=3&fts=1",
            headers=SCREENER_HEADERS, timeout=8
        )
        data = r.json()
        for item in data:
            if item.get("url") and item.get("name"):
                # Extract slug from URL like /company/RELIANCE/consolidated/
                match = re.search(r'/company/([^/]+)/', item["url"])
                if match:
                    return match.group(1)
    except: pass
    return base  # fallback to raw base

def _get_industry_url_from_screener(slug: str):
    """Scrape the company page to find the most specific sub-industry URL."""
    try:
        url = f"https://www.screener.in/company/{slug}/"
        r = requests.get(url, headers=SCREENER_HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "lxml")

        # Match /market/ links with 2+ path segments (handles 3-level AND 4-level breadcrumbs)
        all_market_links = soup.find_all("a", href=re.compile(r'^/market/[A-Z0-9]+/[A-Z0-9]+'))
        if all_market_links:
            # Pick the most specific (longest URL) — deepest industry classification
            best = max(all_market_links, key=lambda l: len(l["href"]))
            return "https://www.screener.in" + best["href"]
    except: pass
    return None

def _scrape_industry_tickers(industry_url: str, is_indian: bool):
    """Scrape the industry page and extract all company slugs."""
    try:
        r = requests.get(industry_url, headers=SCREENER_HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "lxml")
        # Company links are like /company/RELIANCE/consolidated/ or /company/123456/
        company_links = soup.find_all("a", href=re.compile(r'^/company/[^/]+/'))
        slugs = []
        for link in company_links:
            match = re.match(r'^/company/([^/]+)/', link["href"])
            if match:
                slug = match.group(1)
                # Skip pure numeric slugs (BSE codes with no common NSE ticker)
                if not slug.isdigit():
                    slugs.append(slug)
        # Deduplicate preserving order
        seen = set()
        unique_slugs = [s for s in slugs if not (s in seen or seen.add(s))]
        suffix = ".NS" if is_indian else ""
        return [s + suffix for s in unique_slugs[:15]]  # max 15 peers
    except: return []

def get_stock_history(ticker: str, period="1y"):
    stock = yf.Ticker(ticker)
    return stock.history(period=period)

def get_performance_returns(ticker: str):
    benchmark_ticker = "^NSEI" if ticker.endswith(".NS") or ticker.endswith(".BO") else "^GSPC"
    benchmark_name = "Nifty 50" if benchmark_ticker == "^NSEI" else "S&P 500"

    try:
        stock_hist = yf.Ticker(ticker).history(period="max")
    except Exception:
        stock_hist = pd.DataFrame()

    try:
        bench_hist = yf.Ticker(benchmark_ticker).history(period="max")
    except Exception:
        bench_hist = pd.DataFrame()

    if stock_hist.empty or bench_hist.empty:
        return None, benchmark_name

    def calc_return(df, start_date):
        try:
            valid_starts = df.loc[df.index >= pd.Timestamp(start_date).tz_localize(df.index.tz)]
            if valid_starts.empty: return None
            return ((df['Close'].iloc[-1] - valid_starts['Close'].iloc[0]) / valid_starts['Close'].iloc[0]) * 100
        except: return None

    today = datetime.date.today()
    timeframes = {
        "YTD": datetime.date(today.year, 1, 1),
        "1-Year": today - relativedelta(years=1),
        "3-Year": today - relativedelta(years=3),
        "5-Year": today - relativedelta(years=5)
    }
    returns = {}
    for period_name, start_date in timeframes.items():
        returns[period_name] = {
            'Stock': calc_return(stock_hist, start_date),
            'Benchmark': calc_return(bench_hist, start_date)
        }
    return returns, benchmark_name

def get_key_ratios(ticker: str):
    """Returns profitability, leverage, and efficiency ratios."""
    stock = yf.Ticker(ticker)
    info = stock.info
    is_indian = ticker.endswith(".NS") or ticker.endswith(".BO")

    try:
        inc = stock.financials
        bs = stock.balance_sheet
        if inc.empty or bs.empty:
            return None

        def safe_get(df, row):
            for r in row if isinstance(row, list) else [row]:
                if r in df.index: return df.loc[r]
            return pd.Series(dtype=float)

        revenue = safe_get(inc, ['Total Revenue', 'Operating Revenue'])
        net_income = safe_get(inc, ['Net Income', 'Net Income From Continuing Operations'])
        op_income = safe_get(inc, ['Operating Income', 'EBIT'])
        interest_exp = safe_get(inc, ['Interest Expense', 'Interest And Debt Expense'])
        total_assets = safe_get(bs, 'Total Assets')
        total_equity = safe_get(bs, ['Stockholders Equity', 'Common Stock Equity'])
        total_debt = safe_get(bs, ['Total Debt', 'Long Term Debt'])
        current_assets = safe_get(bs, 'Current Assets')
        current_liab = safe_get(bs, 'Current Liabilities')

        divisor = 1e7 if is_indian else 1e6

        ratios = {}
        cols = inc.columns.tolist()
        for col in cols:
            col_label = str(col).split(" ")[0]
            row = {}
            try: row['Net Margin (%)'] = round((net_income[col] / revenue[col]) * 100, 2) if revenue[col] != 0 else None
            except: row['Net Margin (%)'] = None
            try: row['Operating Margin (%)'] = round((op_income[col] / revenue[col]) * 100, 2) if revenue[col] != 0 else None
            except: row['Operating Margin (%)'] = None
            try: row['ROE (%)'] = round((net_income[col] / total_equity[col]) * 100, 2) if total_equity[col] != 0 else None
            except: row['ROE (%)'] = None
            try: row['ROA (%)'] = round((net_income[col] / total_assets[col]) * 100, 2) if total_assets[col] != 0 else None
            except: row['ROA (%)'] = None
            try: row['D/E Ratio'] = round(total_debt[col] / total_equity[col], 2) if total_equity[col] != 0 else None
            except: row['D/E Ratio'] = None
            try: row['Current Ratio'] = round(current_assets[col] / current_liab[col], 2) if current_liab[col] != 0 else None
            except: row['Current Ratio'] = None
            try: row['Interest Coverage'] = round(op_income[col] / abs(interest_exp[col]), 2) if interest_exp[col] != 0 else None
            except: row['Interest Coverage'] = None
            ratios[col_label] = row

        return pd.DataFrame(ratios).T
    except Exception as e:
        return None

def _scrape_peer_table_from_screener(industry_url: str, target_slug: str, is_indian: bool):
    """
    Scrape the full peer comparison table directly from Screener's industry page.
    Returns a DataFrame with CMP, P/E, Market Cap, Div Yield, NP Qtr, ROCE etc.
    """
    import io
    try:
        r = requests.get(industry_url, headers=SCREENER_HEADERS, timeout=10)
        tables = pd.read_html(io.StringIO(r.text))
        if not tables:
            return None
        df = tables[0].copy()

        # Standardise column names
        col_map = {}
        for c in df.columns:
            cl = str(c).lower()
            if 'name' in cl: col_map[c] = 'Company'
            elif 'cmp' in cl or 'price' in cl: col_map[c] = 'CMP'
            elif 'p/e' in cl or 'pe' in cl: col_map[c] = 'P/E'
            elif 'mar cap' in cl or 'mkt cap' in cl or 'market cap' in cl:
                col_map[c] = 'Mkt Cap (Cr)' if is_indian else 'Mkt Cap (B)'
            elif 'div' in cl and 'yld' in cl or 'div' in cl and 'yield' in cl: col_map[c] = 'Div Yld (%)'
            elif 'np qtr' in cl or 'net profit' in cl: col_map[c] = 'NP Qtr (Cr)'
            elif 'qtr profit var' in cl: col_map[c] = 'Profit Var (%)'
            elif 'sales qtr' in cl: col_map[c] = 'Sales Qtr (Cr)'
            elif 'qtr sales var' in cl: col_map[c] = 'Sales Var (%)'
            elif 'roce' in cl: col_map[c] = 'ROCE (%)'
        df.rename(columns=col_map, inplace=True)

        # Drop serial number column
        df = df[[c for c in df.columns if c not in ['S.No.', 'S.No']]]

        # Also get the ticker slugs from href links in the HTML
        soup = BeautifulSoup(r.text, "lxml")
        company_links = soup.find_all("a", href=re.compile(r'^/company/[^/]+/'))
        seen = set()
        slugs = []
        for link in company_links:
            m = re.match(r'^/company/([^/]+)/', link["href"])
            if m:
                s = m.group(1)
                if not s.isdigit() and s not in seen:
                    seen.add(s)
                    slugs.append(s)

        suffix = ".NS" if is_indian else ""
        tickers = [s + suffix for s in slugs]

        # Attach Ticker column (align by row count)
        ticker_col = tickers[:len(df)]
        if len(ticker_col) < len(df):
            ticker_col += [''] * (len(df) - len(ticker_col))
        df.insert(0, 'Ticker', ticker_col)
        df = df[df['Ticker'] != ''].copy()
        df.set_index('Ticker', inplace=True)

        cap_col = 'Mkt Cap (Cr)' if is_indian else 'Mkt Cap (B)'
        if cap_col in df.columns:
            df = df.sort_values(cap_col, ascending=False)

        return df
    except Exception as e:
        return None


def get_sector_peers(ticker: str):
    """
    1. Try to scrape the full peer table in one shot from Screener.in industry page.
    2. Fall back to individual yfinance calls if scraping fails.
    """
    is_indian = ticker.endswith(".NS") or ticker.endswith(".BO")

    if is_indian:
        slug = _get_screener_slug(ticker)
        industry_url = _get_industry_url_from_screener(slug)

        if industry_url:
            # ── PRIMARY: Scrape Screener table directly ──────────────
            df = _scrape_peer_table_from_screener(industry_url, slug, is_indian)
            if df is not None and not df.empty:
                return df, ticker

            # ── FALLBACK: Get ticker list then yfinance ──────────────
            peers = _scrape_industry_tickers(industry_url, is_indian=True)
        else:
            peers = []
    else:
        stock = yf.Ticker(ticker)
        sector = stock.info.get('sector', '')
        us_peers = {
            "Technology":            ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "INTC", "ORCL"],
            "Financial Services":    ["JPM", "BAC", "WFC", "GS", "MS", "C", "AXP"],
            "Healthcare":            ["JNJ", "PFE", "MRK", "ABBV", "UNH", "BMY", "AMGN"],
            "Consumer Cyclical":     ["AMZN", "TSLA", "HD", "NKE", "MCD", "SBUX"],
            "Energy":                ["XOM", "CVX", "COP", "SLB", "PSX", "VLO"],
            "Industrials":           ["CAT", "GE", "HON", "MMM", "BA", "LMT", "RTX"],
            "Basic Materials":       ["LIN", "APD", "NEM", "FCX", "NUE", "AA"],
            "Communication Services":["GOOGL", "META", "NFLX", "DIS", "CMCSA", "T"],
            "Utilities":             ["NEE", "DUK", "SO", "D", "EXC", "AEP"],
        }
        peers = us_peers.get(sector, [])

    # ── yfinance fallback (for US or when scraping fails) ────────────
    if ticker not in peers:
        peers = [ticker] + [p for p in peers if p != ticker]
    peers = peers[:15]

    divisor = 1e7 if is_indian else 1e9
    cap_label = "Mkt Cap (Cr)" if is_indian else "Mkt Cap (B)"
    rev_label = "Revenue (Cr)" if is_indian else "Revenue (B)"
    rows = []
    for p in peers:
        try:
            pinfo = yf.Ticker(p).info
            if not pinfo.get('shortName'): continue
            rows.append({
                'Ticker': p,
                'Company': pinfo.get('shortName', p),
                cap_label: round(pinfo.get('marketCap', 0) / divisor, 0) if pinfo.get('marketCap') else None,
                'CMP': pinfo.get('currentPrice', pinfo.get('regularMarketPrice')),
                'P/E': round(pinfo.get('trailingPE', 0), 1) if pinfo.get('trailingPE') else None,
                'P/B': round(pinfo.get('priceToBook', 0), 2) if pinfo.get('priceToBook') else None,
                rev_label: round(pinfo.get('totalRevenue', 0) / divisor, 0) if pinfo.get('totalRevenue') else None,
                'Net Margin (%)': round(pinfo.get('profitMargins', 0) * 100, 2) if pinfo.get('profitMargins') else None,
                'ROE (%)': round(pinfo.get('returnOnEquity', 0) * 100, 2) if pinfo.get('returnOnEquity') else None,
                'Div Yield (%)': round(pinfo.get('dividendYield', 0) * 100, 2) if pinfo.get('dividendYield') else None,
            })
        except: pass

    if not rows: return None, ticker
    df = pd.DataFrame(rows).set_index('Ticker')
    df.sort_values(cap_label, ascending=False, inplace=True)
    return df, ticker

def get_dividend_history(ticker: str):
    stock = yf.Ticker(ticker)
    try:
        divs = stock.dividends
        if divs.empty: return None
        divs.index = pd.to_datetime(divs.index)
        annual = divs.resample('YE').sum()
        annual.index = annual.index.year
        return annual
    except: return None


def get_screener_insights(ticker: str):
    """
    Scrapes Pros & Cons from Screener.in company page.
    Returns dict with 'pros' and 'cons' lists.
    Falls back to empty lists if scraping fails.
    """
    slug = _get_screener_slug(ticker) if (ticker.endswith(".NS") or ticker.endswith(".BO")) else ticker.replace(".NS","").replace(".BO","")
    try:
        r = requests.get(f"https://www.screener.in/company/{slug}/", headers=SCREENER_HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "lxml")
        pros = [li.get_text(strip=True) for li in soup.select(".pros li")]
        cons = [li.get_text(strip=True) for li in soup.select(".cons li")]
        return {'pros': pros, 'cons': cons}
    except:
        return {'pros': [], 'cons': []}


def get_credit_ratings(ticker: str):
    """
    Scrapes credit rating links (CRISIL, ICRA, CARE) from Screener.in company page.
    Falls back to empty list if scraping fails.
    """
    if not (ticker.endswith(".NS") or ticker.endswith(".BO")):
        return []  # Credit ratings mostly for Indian stocks
    slug = _get_screener_slug(ticker)
    try:
        r = requests.get(f"https://www.screener.in/company/{slug}/", headers=SCREENER_HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "lxml")
        ratings = []
        seen_hrefs = set()
        for a in soup.select("a[href*='crisil'], a[href*='icra'], a[href*='care']"):
            href = a.get("href", "")
            if href in seen_hrefs: continue
            seen_hrefs.add(href)
            txt = a.get_text(" ", strip=True)
            if not txt or txt in ["[1]", "[2]", "[3]"]: continue
            # Detect agency
            agency = "CRISIL" if "crisil" in href else ("ICRA" if "icra" in href else "CARE")
            ratings.append({'agency': agency, 'label': txt, 'url': href})
        return ratings
    except:
        return []

def get_news_with_sentiment(ticker: str, max_news=12):
    """
    Fetches news from yfinance (handles both old flat and new nested content formats)
    and tags each headline with Positive / Negative / Neutral sentiment.
    """
    stock = yf.Ticker(ticker)
    try:
        news = stock.news
        if not news: return []

        positive_words = ['surge', 'beat', 'record', 'growth', 'profit', 'buy', 'upgrade',
                          'strong', 'gain', 'rise', 'rally', 'outperform', 'boost', 'positive',
                          'target', 'expand', 'launch', 'award', 'win', 'milestone', 'peak']
        negative_words = ['fall', 'drop', 'loss', 'miss', 'sell', 'downgrade', 'weak',
                          'decline', 'cut', 'warning', 'risk', 'concern', 'negative', 'trouble',
                          'crash', 'penalty', 'fraud', 'lawsuit', 'probe', 'fine', 'slump']
        results = []
        for item in news[:max_news]:
            # ── New yfinance format: data nested inside item['content'] ──
            content = item.get('content', {})
            if content and isinstance(content, dict):
                title     = content.get('title', '')
                publisher = (content.get('provider') or {}).get('displayName', '')
                link      = (content.get('clickThroughUrl') or content.get('canonicalUrl') or {}).get('url', '#')
                pub_date  = content.get('pubDate', '')
                summary   = content.get('summary', '')
                thumbnail = None
                thumb_data = content.get('thumbnail') or {}
                resolutions = thumb_data.get('resolutions', [])
                if resolutions:
                    # Pick the smallest thumbnail
                    thumbnail = sorted(resolutions, key=lambda x: x.get('width', 9999))[0].get('url')
            else:
                # ── Old flat format fallback ──
                title     = item.get('title', '')
                publisher = item.get('publisher', '')
                link      = item.get('link', '#')
                pub_date  = ''
                summary   = ''
                thumbnail = None

            if not title: continue

            title_lower = title.lower()
            pos_score = sum(1 for w in positive_words if w in title_lower)
            neg_score = sum(1 for w in negative_words if w in title_lower)
            if pos_score > neg_score:   sentiment = "Positive"
            elif neg_score > pos_score: sentiment = "Negative"
            else:                        sentiment = "Neutral"

            results.append({
                'title':     title,
                'publisher': publisher,
                'link':      link,
                'pub_date':  pub_date[:10] if pub_date else '',
                'summary':   summary,
                'thumbnail': thumbnail,
                'sentiment': sentiment
            })
        return results
    except:
        return []


def get_holders(ticker: str):
    stock = yf.Ticker(ticker)
    res = {}
    def format_pct(df):
        if df is None or df.empty: return None
        if 0 in df.columns and 1 in df.columns:
            try:
                numeric_vals = pd.to_numeric(df[0], errors='coerce')
                df = df.copy()
                df[0] = numeric_vals.apply(lambda x: f"{x * 100:.2f}%" if pd.notnull(x) and x <= 1.0 else (str(int(x)) if pd.notnull(x) else x))
            except: pass
        for col in ['% Out', 'pctHeld']:
            if col in df.columns:
                try: df[col] = (pd.to_numeric(df[col], errors='coerce') * 100).map("{:.2f}%".format)
                except: pass
        return df
    try: res['major'] = format_pct(stock.major_holders)
    except: res['major'] = None
    try: res['institutional'] = format_pct(stock.institutional_holders)
    except: res['institutional'] = None
    try: res['mutual_fund'] = format_pct(stock.mutualfund_holders)
    except: res['mutual_fund'] = None
    return res

def get_relative_performance(ticker: str, period="1y"):
    benchmark_ticker = "^NSEI" if ticker.endswith(".NS") or ticker.endswith(".BO") else "^GSPC"
    benchmark_name = "Nifty 50" if benchmark_ticker == "^NSEI" else "S&P 500"
    stock_hist = yf.Ticker(ticker).history(period=period)['Close']
    bench_hist = yf.Ticker(benchmark_ticker).history(period=period)['Close']
    if not stock_hist.empty and not bench_hist.empty:
        df = pd.DataFrame({
            'Stock': (stock_hist / stock_hist.iloc[0]) * 100,
            benchmark_name: (bench_hist / bench_hist.iloc[0]) * 100
        })
        return df, benchmark_name
    return None, benchmark_name

def get_financial_statements(ticker: str, period="Annual"):
    stock = yf.Ticker(ticker)
    is_indian = ticker.endswith(".NS") or ticker.endswith(".BO")
    divisor = 10000000.0 if is_indian else 1000000.0
    label = "in Crores" if is_indian else "in Millions"
    def format_df(df):
        if df is None or df.empty: return None, ""
        df_scaled = df.apply(pd.to_numeric, errors='coerce') / divisor
        try: df_scaled.columns = [str(c).split(' ')[0] for c in df_scaled.columns]
        except: pass
        return df_scaled.round(2), label
    try:
        raw_bs = stock.balance_sheet if period == "Annual" else stock.quarterly_balance_sheet
        bs, bs_label = format_df(raw_bs)
    except: bs, bs_label = None, ""
    try:
        raw_inc = stock.financials if period == "Annual" else stock.quarterly_financials
        inc, inc_label = format_df(raw_inc)
    except: inc, inc_label = None, ""
    return bs, bs_label, inc, inc_label

def get_earnings_history(ticker: str):
    try:
        df = yf.Ticker(ticker).earnings_dates
        if df is not None and not df.empty:
            return df.sort_index(ascending=True).tail(8)
    except: pass
    return None

def get_key_metrics(ticker: str):
    stock = yf.Ticker(ticker)
    info = stock.info
    current_price = info.get('currentPrice', 0)
    previous_close = info.get('previousClose', 0)
    change_pct = ((current_price - previous_close) / previous_close) * 100 if previous_close > 0 else 0.0
    dividend_yield = info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0
    shares_os = info.get('sharesOutstanding', 'N/A')
    if isinstance(shares_os, (int, float)):
        shares_os_str = f"{shares_os / 1e7:.2f} Cr" if (ticker.endswith(".NS") or ticker.endswith(".BO")) else f"{shares_os / 1e6:.2f} M"
    else:
        shares_os_str = shares_os
    try:
        bench_ticker = "^NSEI" if ticker.endswith(".NS") or ticker.endswith(".BO") else "^GSPC"
        bench = yf.Ticker(bench_ticker)
        b_hist = bench.history(period="1d")
        bench_price = round(b_hist['Close'].iloc[-1], 2) if not b_hist.empty else 'N/A'
    except:
        bench_price = 'N/A'
    return {
        "name": info.get('longName', ticker),
        "sector": info.get('sector', 'Unknown Sector'),
        "industry": info.get('industry', 'Unknown Industry'),
        "price": current_price,
        "change_pct": change_pct,
        "target_price": info.get('targetMeanPrice', 'N/A'),
        "pe": info.get('trailingPE', 'N/A'),
        "pb": info.get('priceToBook', 'N/A'),
        "ev_ebitda": info.get('enterpriseToEbitda', 'N/A'),
        "market_cap": info.get('marketCap', 'N/A'),
        "dividend_yield": f"{dividend_yield:.2f}%",
        "shares_os": shares_os_str,
        "52w_high": info.get('fiftyTwoWeekHigh', 'N/A'),
        "52w_low": info.get('fiftyTwoWeekLow', 'N/A'),
        "benchmark_price": bench_price,
        "description": info.get('longBusinessSummary', '')
    }

def get_institutional_data(ticker: str):
    """
    Scrapes Shareholding, Growth CAGR, Cash Flow, and Documents.
    Optimized to use a single page request.
    """
    is_indian = ticker.endswith(".NS") or ticker.endswith(".BO")
    if not is_indian: return None
    
    slug = _get_screener_slug(ticker)
    url = f"https://www.screener.in/company/{slug}/"
    try:
        r = requests.get(url, headers=SCREENER_HEADERS, timeout=12)
        if r.status_code != 200: return None
        soup = BeautifulSoup(r.text, "lxml")
    except: return None

    data = {
        'shareholding': None,
        'growth': [],
        'cash_flow': None,
        'documents': []
    }

    # 1. Shareholding Table
    try:
        shp_sec = soup.find('section', id='shareholding')
        if shp_sec:
            table = shp_sec.find('table')
            if table:
                import io
                df = pd.read_html(io.StringIO(str(table)))[0]
                # Clean up: First column is Category, last columns are dates
                df.columns = [str(c) for c in df.columns]
                data['shareholding'] = df
    except: pass

    # 2. Compounded Growth (ranges-table)
    try:
        growth_tables = soup.find_all('table', class_='ranges-table')
        for gt in growth_tables:
            import io
            df_g = pd.read_html(io.StringIO(str(gt)))[0]
            # Rename columns to just 'Metric' and 'Value'
            df_g.columns = ['Metric', 'Value']
            # The title is in the first row usually or caption
            title = gt.find('th').get_text(strip=True) if gt.find('th') else "Growth"
            data['growth'].append({'title': title, 'df': df_g})
    except: pass

    # 3. Cash Flow Table
    try:
        cf_sec = soup.find('section', id='cash-flow')
        if cf_sec:
            table = cf_sec.find('table')
            if table:
                import io
                df_cf = pd.read_html(io.StringIO(str(table)))[0]
                data['cash_flow'] = df_cf
    except: pass

    # 4. Investor Documents
    try:
        doc_sec = soup.find('section', id='documents')
        if doc_sec:
            for a in doc_sec.find_all('a', href=True):
                title = a.get_text(strip=True)
                url = a['href']
                if not url.startswith('http'):
                    url = "https://www.screener.in" + url
                data['documents'].append({'title': title, 'url': url})
            # Limit to last 12
            data['documents'] = data['documents'][:12]
    except: pass

    return data

def get_screener_financials(ticker: str):
    """
    Scrapes detailed Financials (Quarters, P&L, Balance Sheet) from Screener.in.
    Specifically for Indian stocks. Returns a dict of DataFrames.
    """
    is_indian = ticker.endswith(".NS") or ticker.endswith(".BO")
    if not is_indian: return None

    slug = _get_screener_slug(ticker)
    url = f"https://www.screener.in/company/{slug}/"
    try:
        r = requests.get(url, headers=SCREENER_HEADERS, timeout=12)
        if r.status_code != 200: return None
        soup = BeautifulSoup(r.text, "lxml")
    except: return None

    def clean_df(section_id):
        try:
            sec = soup.find('section', id=section_id)
            if not sec: return None
            table = sec.find('table')
            if not table: return None
            import io
            df = pd.read_html(io.StringIO(str(table)))[0]
            
            # Clean first column (Row Names)
            # Row names have things like "Sales+"
            # We want to remove icons like \ufffd, +, etc.
            if not df.empty:
                def clean_text(text):
                    if not isinstance(text, str): return text
                    # Remove "", "+", and typical expansion icons
                    text = text.replace('\ufffd', '').replace('+', '').strip()
                    # Remove leading/trailing whitespace
                    return text
                df.iloc[:, 0] = df.iloc[:, 0].apply(clean_text)
                
                # Rename the first column to "Metrics"
                cols = list(df.columns)
                cols[0] = "Metrics"
                df.columns = cols
                df.set_index("Metrics", inplace=True)
            return df
        except: return None

    return {
        'quarters': clean_df('quarters'),
        'pnl': clean_df('profit-loss'),
        'balance_sheet': clean_df('balance-sheet')
    }
