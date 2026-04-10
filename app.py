import os
import sys
import io
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from smolagents import ToolCallingAgent, LiteLLMModel
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from tools import get_stock_fundamentals, get_latest_news, get_sector_trends
from data_fetcher import (
    get_stock_history, get_financial_statements, get_key_metrics,
    get_relative_performance, get_performance_returns,
    get_holders, get_earnings_history,
    get_key_ratios, get_sector_peers, get_dividend_history,
    get_news_with_sentiment, get_screener_insights, get_credit_ratings,
    get_institutional_data, get_screener_financials
)

# Load environment variables from .env file in the same directory
load_dotenv()

st.set_page_config(page_title="Institutional Equity Research", page_icon="📈", layout="wide")

# ─── Custom CSS ───────────────────────────────────────────────
st.markdown("""
<style>
    .kpi-card { background: rgba(255,255,255,0.05); border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; }
    .peer-highlight { background: rgba(255, 215, 0, 0.15) !important; font-weight: bold; }
    .sentiment-positive { color: #00c853; font-weight: bold; }
    .sentiment-negative { color: #ff1744; font-weight: bold; }
    .sentiment-neutral { color: #90a4ae; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.title("📈 Institutional Equity Research Report")
st.markdown("Automated Wall Street-grade analysis powered by **Mistral AI** & Yahoo Finance.")

# ─── SIDEBAR ──────────────────────────────────────────────────
st.sidebar.header("⚙️ Configuration")
default_key = os.getenv("MISTRAL_API_KEY", "")
api_provider = st.sidebar.selectbox("Choose AI Engine", ["Mistral AI API", "Groq API"])
api_key = st.sidebar.text_input(f"Enter your {api_provider} Key:", value=default_key, type="password")
model_id = "mistral/mistral-large-latest" if api_provider == "Mistral AI API" else "groq/mixtral-8x7b-32768"

agent = None
if api_key:
    try:
        model = LiteLLMModel(model_id=model_id, api_key=api_key)
        agent = ToolCallingAgent(tools=[get_stock_fundamentals, get_latest_news, get_sector_trends], model=model)
    except Exception as e:
        st.sidebar.error(f"Agent init failed: {e}")

st.sidebar.divider()
st.sidebar.header("📥 Export Report")
export_placeholder = st.sidebar.empty()  # We'll fill this after data is loaded

# ─── MAIN INPUT ───────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    ticker = st.text_input("Enter a Stock Ticker (e.g., RELIANCE.NS, HDFCBANK.NS, AAPL):").upper()
with col2:
    st.write(""); st.write("")
    run_btn = st.button("🔍 Generate Institutional Report", use_container_width=True)

# ─────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────
def color_pct(val):
    if isinstance(val, float):
        color = "#00c853" if val >= 0 else "#ff1744"
        return f"<span style='color:{color}; font-weight:bold'>{val:+.2f}%</span>"
    return str(val)

def render_return_box(period_title, ticker_label, bench_label, stock_ret, bench_ret):
    def f(val):
        if val is None: return "N/A"
        color = "#00c853" if val >= 0 else "#ff1744"
        return f"<p style='margin:0; font-size:20px; font-weight:bold; color:{color};'>{val:+.2f}%</p>"
    return f"""
    <div style='background-color:rgba(255,255,255,0.06); padding:16px; border-radius:10px; height:160px; border:1px solid rgba(255,255,255,0.1)'>
        <p style='font-size:14px; font-weight:bold; margin:0 0 8px 0; color:#ffd700; text-transform:uppercase; letter-spacing:0.5px'>{period_title}</p>
        <p style='font-size:11px; margin:0; color:#aaa; font-weight:500'>{ticker_label}</p>
        {f(stock_ret)}
        <div style='margin-top:10px;'>
            <p style='font-size:11px; margin:0; color:#aaa; font-weight:500'>{bench_label}</p>
            {f(bench_ret)}
        </div>
    </div>"""

def build_excel(ticker, inc_df, bs_df, ratios_df, peers_df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        if inc_df is not None:  inc_df.to_excel(writer, sheet_name="Income Statement")
        if bs_df is not None:   bs_df.to_excel(writer, sheet_name="Balance Sheet")
        if ratios_df is not None: ratios_df.to_excel(writer, sheet_name="Key Ratios")
        if peers_df is not None: peers_df.to_excel(writer, sheet_name="Sector Peers")
    buffer.seek(0)
    return buffer

# ─────────────────────────────────────────────────────────────
# MAIN REPORT
# ─────────────────────────────────────────────────────────────
if run_btn and ticker:
    if not api_key:
        st.error("Please enter your API Key in the sidebar!"); st.stop()

    with st.spinner("Fetching company data..."):
        metrics = get_key_metrics(ticker)
        is_indian = ticker.endswith(".NS") or ticker.endswith(".BO")
        divisor_label = "Cr" if is_indian else "B"
        mc_divisor = 1e7 if is_indian else 1e9

    # ── TOP HEADER ────────────────────────────────────────────
    st.header(f"🏢 {metrics['name']}")
    st.caption(f"**{metrics['sector']}** · {metrics['industry']}")

    # 52-Week Range Visual Bar
    low_52 = metrics['52w_low']
    high_52 = metrics['52w_high']
    cmp = metrics['price']
    if all(isinstance(v, (int, float)) for v in [low_52, high_52, cmp]) and high_52 > low_52:
        pct_pos = ((cmp - low_52) / (high_52 - low_52)) * 100
        st.markdown(f"""
        <div style='margin:8px 0 4px; font-size:13px; color:#aaa'>
            📍 52-Week Range &nbsp;&nbsp; <b style='color:#ff6961'>{low_52:.2f}</b> ──────
            <span style='background:#ffd700;color:#000;padding:2px 8px;border-radius:12px;font-weight:bold'>{cmp:.2f}</span>
            ────── <b style='color:#77dd77'>{high_52:.2f}</b>
            &nbsp;&nbsp; CMP is at <b>{pct_pos:.1f}%</b> of its 52-week range
        </div>""", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    mc = metrics['market_cap']
    mc_str = f"{mc/mc_divisor:.2f} {divisor_label}" if isinstance(mc, (int, float)) else "N/A"

    with c1:
        chg_color = "#00c853" if metrics['change_pct'] >= 0 else "#ff1744"
        st.markdown(f"""<div class='kpi-card'>
            <p style='margin:0;color:#aaa;font-size:12px'>CMP</p>
            <p style='margin:0;font-size:22px;font-weight:bold'>{cmp:.2f} <span style='font-size:14px;color:{chg_color}'>{metrics['change_pct']:+.2f}%</span></p>
            <p style='margin:4px 0 0;font-size:12px'>Target: <b>{metrics['target_price']}</b></p>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class='kpi-card'>
            <p style='margin:0;color:#aaa;font-size:12px'>Market Cap</p>
            <p style='margin:0;font-size:22px;font-weight:bold'>{mc_str}</p>
            <p style='margin:4px 0 0;font-size:12px'>Shares O/S: <b>{metrics['shares_os']}</b></p>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class='kpi-card'>
            <p style='margin:0;color:#aaa;font-size:12px'>Valuation</p>
            <p style='margin:0;font-size:18px;font-weight:bold'>P/E: {metrics['pe']}</p>
            <p style='margin:4px 0 0;font-size:12px'>P/B: <b>{metrics['pb']}</b> &nbsp;|&nbsp; EV/EBITDA: <b>{metrics['ev_ebitda']}</b></p>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class='kpi-card'>
            <p style='margin:0;color:#aaa;font-size:12px'>{metrics['benchmark_price'] and "Nifty 50" or "Benchmark"}</p>
            <p style='margin:0;font-size:22px;font-weight:bold'>{metrics['benchmark_price']}</p>
            <p style='margin:4px 0 0;font-size:12px'>Div Yield: <b>{metrics['dividend_yield']}</b> &nbsp;|&nbsp; 52W: {low_52}/{high_52}</p>
        </div>""", unsafe_allow_html=True)

    # Company Description
    if metrics.get('description'):
        with st.expander("📄 About the Company"):
            st.write(metrics['description'])

    st.divider()

    # ── PERFORMANCE RETURNS ────────────────────────────────────
    st.subheader("📊 Long-Term Performance Returns")
    returns_data, bench_name = get_performance_returns(ticker)
    if returns_data:
        p1, p2, p3, p4 = st.columns(4)
        for col, key, label in zip([p1,p2,p3,p4], ["YTD","1-Year","3-Year","5-Year"], ["YTD Return","1-Year Return","3-Year Return","5-Year Return"]):
            col.markdown(render_return_box(label, ticker, bench_name, returns_data[key]['Stock'], returns_data[key]['Benchmark']), unsafe_allow_html=True)
    else:
        st.warning("Insufficient historical data.")

    st.divider()

    # ── AI RECOMMENDATION ─────────────────────────────────────
    st.subheader("💡 AI Analyst Thesis & Recommendation")
    with st.spinner("AI Agent researching sector, fundamentals, catalysts & risks..."):
        prompt = f"""
        You are a top-tier Wall Street Equity Analyst writing about {ticker}.
        
        CRITICAL FORMAT:
        1. First line MUST be: **RATING: BUY**, **RATING: HOLD**, or **RATING: SELL**
        
        2. Write a 4-paragraph institutional thesis:
        - **Company Fundamentals:** Current valuation and financial health.
        - **Sector & Industry Overview:** (USE get_sector_trends tool for macro context)
        - **Growth Catalysts:** What will drive price appreciation.
        - **Key Risks:** What could go wrong.
        """
        try:
            ai_response = agent.run(prompt)
            st.info(ai_response)
        except Exception as e:
            st.error(f"AI analysis failed: {e}")

    st.divider()

    # ── DATA TABS ─────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
        "📈 Relative Performance", "🕯️ Price Chart", "📋 Financials",
        "📰 News & Sentiment", "🏦 Holders", "💰 Earnings",
        "🏭 Sector Positioning", "📊 Ratios & Dividends", "🔬 Institutional Insights"
    ])

    with tab1:
        st.subheader("Normalized 1-Year Performance vs Benchmark")
        rel_df, bench_plot_name = get_relative_performance(ticker)
        if rel_df is not None:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=rel_df.index, y=rel_df['Stock'], name=ticker, line=dict(color='#ffd700', width=2.5)))
            fig.add_trace(go.Scatter(x=rel_df.index, y=rel_df[bench_plot_name], name=bench_plot_name, line=dict(color='#ffffff', width=2.5)))
            fig.add_hline(y=100, line_dash="dot", line_color="gray", opacity=0.5)
            fig.update_layout(height=450, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("1-Year Candlestick Chart")
        hist = get_stock_history(ticker)
        if hist is not None and not hist.empty:
            fig2 = go.Figure(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'],
                                            increasing_line_color='#00c853', decreasing_line_color='#ff1744'))
            # Volume bars
            fig2.add_trace(go.Bar(x=hist.index, y=hist['Volume'], name='Volume', yaxis='y2',
                                  marker_color='rgba(100,100,255,0.3)'))
            fig2.update_layout(
                height=550, xaxis_rangeslider_visible=False,
                yaxis2=dict(overlaying='y', side='right', showgrid=False),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig2, use_container_width=True)

    with tab3:
        st.subheader("Financial Statements")
        period_fs = st.radio("Period:", ["Annual", "Quarterly"], horizontal=True, key="fs_toggle")
        bs, bs_label, inc, inc_label = get_financial_statements(ticker, period=period_fs)
        st.markdown(f"**Income Statement ({period_fs}) — {inc_label}**")
        if inc is not None: st.dataframe(inc.style.format("{:,.2f}", na_rep="—"), use_container_width=True)
        else: st.info("Income statement not available.")
        st.markdown(f"**Balance Sheet ({period_fs}) — {bs_label}**")
        if bs is not None: st.dataframe(bs.style.format("{:,.2f}", na_rep="—"), use_container_width=True)
        else: st.info("Balance sheet not available.")

    with tab4:
        st.subheader("News & Sentiment Analysis")
        news_items = get_news_with_sentiment(ticker)
        if news_items:
            for item in news_items:
                s = item['sentiment']
                badge_color = "#00c853" if s == "Positive" else ("#ff1744" if s == "Negative" else "#90a4ae")
                st.markdown(f"""<div style='padding:10px; margin-bottom:8px; border-left:4px solid {badge_color}; background:rgba(255,255,255,0.04); border-radius:4px'>
                    <span style='font-size:11px; color:{badge_color}; font-weight:bold'>● {s}</span>
                    &nbsp;&nbsp;<span style='color:#aaa; font-size:11px'>{item['publisher']}</span><br>
                    <a href="{item['link']}" target="_blank" style='color:white; text-decoration:none; font-size:14px'><b>{item['title']}</b></a>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("No recent news found.")

    with tab5:
        st.subheader("🤝 Shareholding Analysis")
        if is_indian:
            inst_data = get_institutional_data(ticker)
            if inst_data and inst_data['shareholding'] is not None:
                st.markdown("### Quarterly Shareholding Pattern (%)")
                shp = inst_data['shareholding']
                
                # Exclude 'No. of Shareholders' from the display table too for a cleaner look
                shp_clean = shp[~shp.iloc[:,0].str.contains('No. of Shareholders', na=False, case=False)].copy()
                st.dataframe(shp_clean.style.format(na_rep="—"), use_container_width=True)
                
                st.divider()
                st.markdown("### Institutional Summary")
                # Summary metrics
                latest_col = shp_clean.columns[-1]
                # Filter categories and clean their names
                sum_df = shp_clean.copy()
                sum_df.iloc[:,0] = sum_df.iloc[:,0].str.replace('+', '', regex=False).str.strip()
                
                sum_cols = st.columns(len(sum_df))
                for i, row in enumerate(sum_df.itertuples(index=False)):
                    with sum_cols[i % len(sum_df)]:
                        name = getattr(row, sum_df.columns[0])
                        val = getattr(row, latest_col)
                        st.metric(name, val)
            else:
                st.info("Institutional shareholding data not available for this ticker.")
        else:
            # Fallback to yfinance for International stocks
            holders = get_holders(ticker)
            h1, h2 = st.columns(2)
            with h1:
                st.markdown("**📌 Major Holders**")
                if holders['major'] is not None: st.dataframe(holders['major'], use_container_width=True)
                else: st.info("Not available.")
            with h2:
                st.markdown("**🏛️ Institutional & Mutual Funds**")
                if holders['institutional'] is not None: st.dataframe(holders['institutional'], use_container_width=True)
                elif holders['mutual_fund'] is not None: st.dataframe(holders['mutual_fund'], use_container_width=True)
                else: st.info("Not available.")

    with tab6:
        st.subheader("Earnings Analysis")
        col_eps, col_rev = st.columns(2)
        with col_eps:
            st.markdown("**Earnings Per Share — Estimate vs Actual**")
            earn_hist = get_earnings_history(ticker)
            if earn_hist is not None and not earn_hist.empty:
                dates = earn_hist.index.strftime('%b %Y')
                est = earn_hist['EPS Estimate']
                act = earn_hist['Reported EPS']
                colors = ['#00c853' if (pd.notnull(a) and pd.notnull(e) and a >= e) else '#ff1744' for a, e in zip(act, est)]
                fig_eps = go.Figure()
                fig_eps.add_trace(go.Scatter(x=dates, y=est, mode='markers+lines', name='Estimate',
                                             line=dict(color='#aaa', dash='dot'),
                                             marker=dict(color='white', size=12, symbol='circle-open', line=dict(width=2))))
                fig_eps.add_trace(go.Scatter(x=dates, y=act, mode='markers', name='Actual',
                                             marker=dict(color=colors, size=10)))
                for i, (d, a, e) in enumerate(zip(dates, act, est)):
                    if pd.notnull(a) and pd.notnull(e):
                        diff = a - e
                        label = f"+{diff:.2f}" if diff >= 0 else f"{diff:.2f}"
                        color = '#00c853' if diff >= 0 else '#ff1744'
                        fig_eps.add_annotation(x=d, y=a, text=f"<b>{label}</b>", showarrow=False, yshift=-20, font=dict(color=color, size=10))
                fig_eps.update_layout(height=380, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', hovermode="x unified")
                st.plotly_chart(fig_eps, use_container_width=True)
            else:
                st.info("EPS history not available.")

        if is_indian:
            # ── Screener Financials (Indian Stocks) ───────────────────
            fin_data = get_screener_financials(ticker)
            if fin_data:
                st.markdown("### 📊 Quarterly Results")
                if fin_data['quarters'] is not None:
                    st.dataframe(fin_data['quarters'].style.format(na_rep="—"), use_container_width=True)
                
                st.divider()

                mcol1, mcol2 = st.columns([2, 1])
                with mcol1:
                    st.markdown("### 📈 Profit & Loss (Annual)")
                    if fin_data['pnl'] is not None:
                        st.dataframe(fin_data['pnl'].style.format(na_rep="—"), use_container_width=True)
                
                with mcol2:
                    st.markdown("#### Performance Trend")
                    if fin_data['pnl'] is not None:
                        # Extract Sales and Net Profit for Chart
                        pnl = fin_data['pnl']
                        rev_row = next((r for r in pnl.index if 'Sales' in r), None)
                        earn_row = next((r for r in pnl.index if 'Net Profit' in r), None)
                        if rev_row and earn_row:
                            # Drop TTM for charting clean history
                            plot_cols = [c for c in pnl.columns if c != 'TTM']
                            plot_df = pnl.loc[[rev_row, earn_row], plot_cols].T
                            # Convert to numeric
                            plot_df = plot_df.apply(pd.to_numeric, errors='coerce')
                            
                            fig_bar = go.Figure()
                            fig_bar.add_trace(go.Bar(x=plot_df.index, y=plot_df[rev_row], name='Sales', marker_color='#3498db', opacity=0.85))
                            fig_bar.add_trace(go.Bar(x=plot_df.index, y=plot_df[earn_row], name='Profit', marker_color='#f39c12', opacity=0.85))
                            fig_bar.update_layout(barmode='group', height=350, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', bargap=0.2, margin=dict(l=0,r=0,t=20,b=20))
                            st.plotly_chart(fig_bar, use_container_width=True)

                st.divider()
                st.markdown("### 🏦 Balance Sheet")
                if fin_data['balance_sheet'] is not None:
                    st.dataframe(fin_data['balance_sheet'].style.format(na_rep="—"), use_container_width=True)
            else:
                st.info("Institutional financials not available for this ticker.")
        else:
            # ── yfinance Financials (International Stocks) ────────────
            col_rev, col_eps = st.columns(2)
            with col_rev:
                st.markdown("**Revenue vs. Net Earnings**")
                period_rev = st.radio("Period:", ["Annual", "Quarterly"], horizontal=True, key="rev_toggle")
                _, _, inc_df, _ = get_financial_statements(ticker, period=period_rev)
                if inc_df is not None and not inc_df.empty:
                    rev_row = next((r for r in ['Total Revenue', 'Operating Revenue'] if r in inc_df.index), None)
                    earn_row = next((r for r in ['Net Income', 'Net Income From Continuing Operations'] if r in inc_df.index), None)
                    if rev_row and earn_row:
                        plot_df = inc_df.loc[[rev_row, earn_row]].T.sort_index(ascending=True)
                        fig_bar = go.Figure()
                        fig_bar.add_trace(go.Bar(x=plot_df.index, y=plot_df[rev_row], name='Revenue', marker_color='#3498db', opacity=0.85))
                        fig_bar.add_trace(go.Bar(x=plot_df.index, y=plot_df[earn_row], name='Net Earnings', marker_color='#f39c12', opacity=0.85))
                        fig_bar.update_layout(barmode='group', height=380, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', bargap=0.2)
                        st.plotly_chart(fig_bar, use_container_width=True)
                    else:
                        st.info("Could not find Revenue/Earnings rows.")
                else:
                    st.info("Financials not available.")
            
            with col_eps:
                st.markdown("**EPS & Earnings Surprise**")
                # ... Existing EPS chart logic ...

    with tab7:
        st.subheader("🏭 Sector Positioning & Peer Comparison")

        # ── Institutional Pros & Cons ────────────────────────────────
        with st.spinner("Fetching institutional insights & peer data..."):
            insights = get_screener_insights(ticker)
            ratings  = get_credit_ratings(ticker)
            peers_df, target = get_sector_peers(ticker)

        if insights['pros'] or insights['cons']:
            pc1, pc2 = st.columns(2)
            with pc1:
                st.markdown("**✅ Pros**")
                for p in insights['pros']:
                    st.markdown(f"<div style='background:rgba(0,200,83,0.1);border-left:3px solid #00c853;padding:6px 10px;margin:4px 0;border-radius:4px;font-size:13px'>✔ {p}</div>", unsafe_allow_html=True)
            with pc2:
                st.markdown("**❌ Cons**")
                for c in insights['cons']:
                    st.markdown(f"<div style='background:rgba(255,23,68,0.1);border-left:3px solid #ff1744;padding:6px 10px;margin:4px 0;border-radius:4px;font-size:13px'>✖ {c}</div>", unsafe_allow_html=True)
            st.divider()
        else:
            if is_indian:
                st.info("Institutional Pros/Cons not available for this specific company.")
            st.divider()

        # ── Credit Ratings ───────────────────────────────────────────
        if ratings:
            st.markdown("**🏦 Credit Ratings**")
            r_cols = st.columns(min(len(ratings), 3))
            for i, r in enumerate(ratings[:3]):
                badge = "#27ae60" if "AAA" in r['label'] or "AA" in r['label'] else "#e67e22"
                r_cols[i % 3].markdown(f"""
                <div style='background:rgba(255,255,255,0.06);padding:10px;border-radius:6px;border-top:3px solid {badge}'>
                    <span style='font-size:11px;color:#aaa'>{r['agency']}</span><br>
                    <a href="{r['url']}" target="_blank" style='color:white;font-size:13px'>{r['label']}</a>
                </div>""", unsafe_allow_html=True)
            st.divider()

        # ── Peer Table ───────────────────────────────────────────────
        if peers_df is not None:
            cap_col = [c for c in peers_df.columns if 'Mkt Cap' in c]
            cap_col = cap_col[0] if cap_col else None
            st.markdown(f"Showing **{len(peers_df)} sector peers** ranked by Market Cap. Your stock highlighted in **gold**.")

            def highlight_row(row):
                if row.name == target:
                    return ['background-color: rgba(255,215,0,0.18); font-weight:bold; color:#ffd700'] * len(row)
                return [''] * len(row)

            # Convert all numeric columns safely (Screener data comes as strings)
            for col in peers_df.columns:
                if col != 'Company':
                    peers_df[col] = pd.to_numeric(peers_df[col], errors='coerce')

            st.dataframe(peers_df.style.apply(highlight_row, axis=1).format(na_rep="—"), use_container_width=True, height=420)

    with tab9:
        inst_data = get_institutional_data(ticker)
        if inst_data:
            st.subheader("🔬 Institutional Intelligence Dashboard")
            
            # --- Ownership Structure ---
            st.markdown("### 🤝 Ownership Structure")
            shp = inst_data['shareholding']
            if shp is not None:
                # Filter out 'No. of Shareholders' as it explodes the chart scale
                shp_filtered = shp[~shp.iloc[:, 0].str.contains('No. of Shareholders', na=False, case=False)].copy()
                
                # Latest quarter is the last column
                latest_col = shp_filtered.columns[-1]
                # Clean names (remove +)
                categories = shp_filtered.iloc[:, 0].str.replace('+', '', regex=False).str.strip().tolist()
                values = pd.to_numeric(shp_filtered[latest_col].str.replace('%',''), errors='coerce').fillna(0).tolist()
                
                fig_shp = go.Figure(data=[go.Pie(
                    labels=categories, values=values, hole=.4,
                    marker_colors=['#ffd700', '#3498db', '#2ecc71', '#e74c3c', '#9b59b6', '#f39c12']
                )])
                fig_shp.update_layout(
                    showlegend=True, margin=dict(t=0, b=0, l=0, r=0),
                    height=300, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_shp, use_container_width=True)
                
                with st.expander("Show Historical Ownership Table"):
                    st.dataframe(shp, use_container_width=True)
            
            st.divider()

            # --- Multi-Year Growth ---
            st.markdown("### 📉 Multi-Year Growth Track")
            growth_counts = len(inst_data['growth'])
            if growth_counts > 0:
                gcols = st.columns(2) # Show growth tables in 2 columns to save vertical space but still "one by one" flow
                for i, growth in enumerate(inst_data['growth']):
                    with gcols[i % 2]:
                        st.markdown(f"**{growth['title']}**")
                        st.table(growth['df'])
            
            st.divider()

            # --- Cash Flows ---
            st.markdown("### 💸 Corporate Cash Flow Statement")
            cf = inst_data['cash_flow']
            if cf is not None:
                st.dataframe(cf.style.format(na_rep="—"), use_container_width=True)
            
            st.divider()

            # --- Investor Documents ---
            st.markdown("### 📂 Investor Documents & Library")
            docs = inst_data['documents']
            if docs:
                # Show in a grid
                dcols = st.columns(3)
                for i, doc in enumerate(docs):
                    with dcols[i % 3]:
                        icon = "📄"
                        if "PPT" in doc['title'].upper() or "PRESENTATION" in doc['title'].upper(): icon = "📊"
                        if "TRANSCRIPT" in doc['title'].upper(): icon = "🎙️"
                        if "REC" in doc['title'].upper() or "VIDEO" in doc['title'].upper(): icon = "🎥"
                        
                        st.markdown(f"""
                        <div style='background:rgba(255,255,255,0.05); padding:10px; border-radius:8px; margin-bottom:10px; border-left:4px solid #ffd700'>
                            <p style='margin:0; font-size:13px; font-weight:bold;'>{icon} {doc['title']}</p>
                            <a href='{doc['url']}' target='_blank' style='font-size:11px; color:#3498db'>View Document ↗</a>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("No corporate documents found for this period.")
        else:
            if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
                st.info("Institutional Deep-Dive is currently optimized for Indian stocks.")
            else:
                st.info("Advanced institutional data not available for this ticker.")

            # P/E ranking bar chart
            if 'P/E' in peers_df.columns:
                pe_data = pd.to_numeric(peers_df['P/E'], errors='coerce').dropna().sort_values(ascending=True)
                if not pe_data.empty:
                    colors_bar = ['#ffd700' if idx == target else '#3498db' for idx in pe_data.index]
                    fig_pe = go.Figure(go.Bar(
                        x=pe_data.values, y=pe_data.index, orientation='h',
                        marker_color=colors_bar,
                        text=[f"{v:.1f}x" for v in pe_data.values], textposition='outside'
                    ))
                    fig_pe.update_layout(
                        title="P/E Ratio Ranking (lower = cheaper)",
                        height=max(300, len(pe_data) * 40),
                        xaxis_title="P/E Ratio",
                        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_pe, use_container_width=True)

            # ROCE % ranking chart (available from Screener)
            roce_col = next((c for c in peers_df.columns if 'ROCE' in c), None)
            if roce_col:
                roce_data = pd.to_numeric(peers_df[roce_col], errors='coerce').dropna().sort_values(ascending=True)
                if not roce_data.empty:
                    roce_colors = ['#ffd700' if idx == target else '#2ecc71' for idx in roce_data.index]
                    fig_roce = go.Figure(go.Bar(
                        x=roce_data.values, y=roce_data.index, orientation='h',
                        marker_color=roce_colors,
                        text=[f"{v:.1f}%" for v in roce_data.values], textposition='outside'
                    ))
                    fig_roce.update_layout(
                        title="ROCE % Ranking (higher = better)",
                        height=max(300, len(roce_data) * 40),
                        xaxis_title="ROCE (%)",
                        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_roce, use_container_width=True)
            else:
                st.info("Sector peer data not available for this ticker.")


    with tab8:
        st.subheader("📊 Key Financial Ratios")
        ratios_df = get_key_ratios(ticker)
        if ratios_df is not None:
            st.markdown("**Profitability, Leverage & Efficiency Ratios (Annual)**")
            st.dataframe(ratios_df.style.format("{:.2f}", na_rep="—"), use_container_width=True)
        else:
            st.info("Ratio data not available.")

        st.divider()

        st.subheader("🎯 Dividend History")
        div_hist = get_dividend_history(ticker)
        if div_hist is not None and not div_hist.empty:
            fig_div = go.Figure(go.Bar(
                x=div_hist.index.astype(str),
                y=div_hist.values,
                marker_color='#2ecc71',
                text=[f"{v:.2f}" for v in div_hist.values],
                textposition='outside'
            ))
            fig_div.update_layout(
                title="Annual Dividend Per Share",
                height=350, xaxis_title="Year", yaxis_title="Dividend",
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_div, use_container_width=True)
        else:
            st.info("No dividend history found (company may not pay dividends).")

    # ── EXPORT BUTTONS (Sidebar) ──────────────────────────────
    bs, _, inc, _ = get_financial_statements(ticker)
    ratios_df = get_key_ratios(ticker)
    peers_df, _ = get_sector_peers(ticker)

    excel_buf = build_excel(ticker, inc, bs, ratios_df, peers_df)
    with export_placeholder.container():
        st.download_button(
            label="📥 Download Excel Report",
            data=excel_buf,
            file_name=f"{ticker}_equity_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
