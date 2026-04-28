import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go

st.set_page_config(
    page_title="RetailTraders.nl | Oil Geopolitics Dashboard",
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
    "OVX": "^OVX",
    "Gold": "GC=F",
    "VIX": "^VIX",
    "DXY": "DX-Y.NYB",
    "US 10Y Yield": "^TNX",
}

@st.cache_data(ttl=900)
def load_prices(tickers, period="6mo"):
    raw = yf.download(
        list(tickers.values()),
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False
    )

    if isinstance(raw.columns, pd.MultiIndex):
        data = raw["Close"]
    else:
        data = raw[["Close"]]

    reverse_map = {v: k for k, v in tickers.items()}
    data = data.rename(columns=reverse_map)

    return data.dropna(how="all")


def pct_change(df, days=5):
    return (df.iloc[-1] / df.iloc[-days] - 1) * 100


def score_signal(value, bullish=True):
    if pd.isna(value):
        return 0

    raw = min(max(value, -2), 2) / 2
    return raw if bullish else -raw


prices = load_prices(TICKERS)

st.title("Retailtraders.nl - Oil Geopolitics Signal Dashboard")
st.caption("Focus: OPEC fracture risk, oil structure, energy equities, tankers, volatility, inflation stress.")

latest = prices.iloc[-1]
weekly = pct_change(prices, 5)

xle_spy_ratio = prices["XLE"] / prices["SPY"]
xle_spy_5d = (xle_spy_ratio.iloc[-1] / xle_spy_ratio.iloc[-5] - 1) * 100

tanker_mom = np.nanmean([
    weekly.get("Frontline", np.nan),
    weekly.get("International Seaways", np.nan)
])

brent_mom = weekly.get("Brent", 0)
ovx_mom = weekly.get("OVX", 0)
vix_mom = weekly.get("VIX", 0)
gold_mom = weekly.get("Gold", 0)
dxy_mom = weekly.get("DXY", 0)
yield_mom = weekly.get("US 10Y Yield", 0)

regime_score = round(
    50
    + 8 * score_signal(brent_mom)
    + 12 * score_signal(xle_spy_5d)
    + 12 * score_signal(tanker_mom)
    + 8 * score_signal(gold_mom)
    + 6 * score_signal(ovx_mom)
    + 4 * score_signal(vix_mom),
    1
)

regime_score = max(0, min(100, regime_score))

col1, col2, col3, col4 = st.columns(4)

col1.metric("Oil Geopolitics Score", regime_score)
col2.metric("Brent 5D %", f"{brent_mom:.2f}%")
col3.metric("XLE vs SPY 5D", f"{xle_spy_5d:.2f}%")
col4.metric("Tanker Basket 5D", f"{tanker_mom:.2f}%")

col5, col6, col7, col8 = st.columns(4)

col5.metric("OVX 5D %", f"{ovx_mom:.2f}%")
col6.metric("VIX 5D %", f"{vix_mom:.2f}%")
col7.metric("Gold 5D %", f"{gold_mom:.2f}%")
col8.metric("DXY 5D %", f"{dxy_mom:.2f}%")

st.divider()

left, right = st.columns([2, 1])

with left:
    selected = st.multiselect(
        "Chart assets",
        list(prices.columns),
        default=["Brent", "WTI", "XLE", "Exxon", "Shell", "Gold", "OVX", "VIX"]
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
        yaxis_title="Indexed to 100",
        hovermode="x unified"
    )

    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Signal Engine")

    silent_accumulation = (
        abs(weekly.get("Brent", 0)) < 2
        and xle_spy_5d > 1
        and tanker_mom > 2
    )

    fake_headline = (
        weekly.get("Brent", 0) > 4
        and xle_spy_5d < 0
        and tanker_mom < 1
    )

    hidden_supply_stress = (
        weekly.get("Brent", 0) > 2
        and tanker_mom > 3
        and ovx_mom > 3
    )

    real_crisis = (
        weekly.get("Brent", 0) > 3
        and xle_spy_5d > 1
        and tanker_mom > 3
        and gold_mom > 1
        and ovx_mom > 3
    )

    inflation_stress = (
        weekly.get("Brent", 0) > 2
        and yield_mom > 1
        and dxy_mom > 0
    )

    signals = {
        "Silent Accumulation": silent_accumulation,
        "Fake Headline Move": fake_headline,
        "Hidden Supply Stress": hidden_supply_stress,
        "Real Crisis Mode": real_crisis,
        "Inflation Stress": inflation_stress,
    }

    for name, active in signals.items():
        if active:
            st.error(f"ACTIVE: {name}")
        else:
            st.success(f"Neutral: {name}")

st.divider()

st.subheader("XLE vs SPY Ratio")

ratio_fig = go.Figure()

ratio_fig.add_trace(go.Scatter(
    x=xle_spy_ratio.index,
    y=xle_spy_ratio,
    mode="lines",
    name="XLE / SPY"
))

ratio_fig.update_layout(
    height=350,
    title="Energy Sector Relative Strength vs S&P 500",
    yaxis_title="XLE / SPY Ratio",
    hovermode="x unified"
)

st.plotly_chart(ratio_fig, use_container_width=True)

st.divider()

st.subheader("Latest Market Snapshot")

snapshot = pd.DataFrame({
    "Latest": latest,
    "5D %": weekly
}).round(2)

st.dataframe(snapshot, use_container_width=True)