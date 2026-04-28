import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import plotly.graph_objects as go

st.set_page_config(
    page_title="RetailTraders.nl Oil Geopolitics Dashboard",
    layout="wide"
)

TICKERS = {
    "Brent": "BZ=F",
    "WTI": "CL=F",
    "XLE": "XLE",
    "SPY": "SPY",
    "Exxon": "XOM",
    "Shell": "SHEL",
    "Frontline": "FRO",
    "International Seaways": "INSW",
    "DXY Proxy": "DX-Y.NYB",
    "Gold": "GC=F",
}

@st.cache_data(ttl=900)
def load_prices(tickers, period="6mo"):
    data = yf.download(
        list(tickers.values()),
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False
    )["Close"]
    data.columns = tickers.keys()
    return data.dropna(how="all")

def pct_change(df, days=5):
    return (df.iloc[-1] / df.iloc[-days] - 1) * 100

def zscore(series, window=60):
    return (series.iloc[-1] - series.tail(window).mean()) / series.tail(window).std()

def score_signal(value, bullish=True):
    if np.isnan(value):
        return 0
    raw = min(max(value, -2), 2) / 2
    return raw if bullish else -raw

prices = load_prices(TICKERS)

st.title("Retailtraders.nl - Oil Geopolitics Signal Dashboard")
st.caption("Focus: OPEC fracture risk, oil structure, energy equities, tankers, inflation stress.")

latest = prices.iloc[-1]
weekly = pct_change(prices, 5)

col1, col2, col3, col4 = st.columns(4)

brent_mom = weekly.get("Brent", 0)
xle_rs = weekly.get("XLE", 0) - weekly.get("SPY", 0)
tanker_mom = np.nanmean([
    weekly.get("Frontline", np.nan),
    weekly.get("International Seaways", np.nan)
])
gold_mom = weekly.get("Gold", 0)

regime_score = round(
    50
    + 8 * score_signal(brent_mom)
    + 12 * score_signal(xle_rs)
    + 12 * score_signal(tanker_mom)
    + 8 * score_signal(gold_mom),
    1
)

regime_score = max(0, min(100, regime_score))

col1.metric("Oil Geopolitics Score", regime_score)
col2.metric("Brent 5D %", f"{brent_mom:.2f}%")
col3.metric("XLE vs SPY 5D", f"{xle_rs:.2f}%")
col4.metric("Tanker Basket 5D", f"{tanker_mom:.2f}%")

st.divider()

left, right = st.columns([2, 1])

with left:
    selected = st.multiselect(
        "Chart assets",
        list(prices.columns),
        default=["Brent", "WTI", "XLE", "Exxon", "Shell"]
    )

    fig = go.Figure()
    normalized = prices[selected] / prices[selected].iloc[0] * 100

    for col in normalized.columns:
        fig.add_trace(go.Scatter(
            x=normalized.index,
            y=normalized[col],
            mode="lines",
            name=col
        ))

    fig.update_layout(
        height=500,
        title="Normalized Performance",
        yaxis_title="Indexed to 100"
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Signal Engine")

    silent_accumulation = (
        abs(weekly.get("Brent", 0)) < 2
        and xle_rs > 1
        and tanker_mom > 2
    )

    fake_headline = (
        weekly.get("Brent", 0) > 4
        and xle_rs < 0
        and tanker_mom < 1
    )

    real_crisis = (
        weekly.get("Brent", 0) > 3
        and xle_rs > 1
        and tanker_mom > 3
        and gold_mom > 1
    )

    hidden_supply_stress = (
        weekly.get("Brent", 0) > 2
        and tanker_mom > 3
    )

    signals = {
        "Silent Accumulation": silent_accumulation,
        "Fake Headline Move": fake_headline,
        "Hidden Supply Stress": hidden_supply_stress,
        "Real Crisis Mode": real_crisis,
    }

    for name, active in signals.items():
        if active:
            st.error(f"ACTIVE: {name}")
        else:
            st.success(f"Neutral: {name}")

st.divider()

st.subheader("Latest Market Snapshot")
st.dataframe(
    pd.DataFrame({
        "Latest": latest,
        "5D %": weekly
    }).round(2),
    use_container_width=True
)