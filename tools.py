import yfinance as yf
from smolagents import tool
from duckduckgo_search import DDGS

@tool
def get_stock_fundamentals(ticker: str) -> str:
    """Fetches key financial metrics for a given stock ticker.
    
    Args:
        ticker: The stock ticker symbol (e.g., 'AAPL', 'RELIANCE.NS').
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        pe = info.get('trailingPE', 'N/A')
        fwd_pe = info.get('forwardPE', 'N/A')
        market_cap = info.get('marketCap', 'N/A')
            
        profit_margin = info.get('profitMargins', 'N/A')
        if profit_margin != 'N/A':
            profit_margin = f"{profit_margin * 100:.2f}%"
            
        current_price = info.get('currentPrice', 'N/A')
        
        return f"Recent Data for {ticker}:\nPrice: ${current_price}\nMarket Cap: {market_cap}\nP/E Ratio: {pe}\nForward P/E: {fwd_pe}\nProfit Margin: {profit_margin}"
    except Exception as e:
        return f"Failed to retrieve data for {ticker}. Error: {str(e)}"

@tool
def get_latest_news(ticker: str) -> str:
    """Searches the web for latest financial news for the company.
    
    Args:
        ticker: The stock ticker symbol to search for.
    """
    try:
        results = DDGS().text(f"{ticker} stock financial news", max_results=3)
        news_summary = f"Latest News Headlines for {ticker}:\n"
        for i, res in enumerate(results):
            news_summary += f"{i+1}. {res['title']} - {res['body']}\n"
        return news_summary
    except Exception as e:
        return f"Failed to search news for {ticker}. Error: {str(e)}"

@tool
def get_sector_trends(ticker: str) -> str:
    """Finds the company's industry and searches for global/regional macro trends.
    
    Args:
        ticker: The stock ticker symbol.
    """
    try:
        stock = yf.Ticker(ticker)
        industry = stock.info.get('industry', 'General Market')
        sector = stock.info.get('sector', 'Macro')
        
        # Search DuckDuckGo for broad industry trends
        query = f"Global {industry} industry market trends 2024 2025"
        results = DDGS().text(query, max_results=4)
        
        trend_summary = f"Macro Trends for the {industry} ({sector}) sector:\n"
        for i, res in enumerate(results):
            trend_summary += f"- {res['body']}\n"
            
        return trend_summary
    except Exception as e:
        return f"Failed to retrieve sector trends for {ticker}. Error: {str(e)}"
