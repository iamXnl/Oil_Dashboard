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


ALERT_THRESHOLDS = {
    "Silent Accumulation": {
        "description": "Brent beweegt beperkt, maar energie-aandelen en tankers lopen op. Mogelijke institutionele positionering.",
    },
    "Fake Headline Move": {
        "description": "Brent stijgt hard, maar energie-aandelen en tankers bevestigen niet. Kans op emotionele headline move.",
    },
    "Hidden Supply Stress": {
        "description": "Brent, tankers en olievolatiliteit stijgen tegelijk. Mogelijke fysieke marktstress.",
    },
    "Real Crisis Mode": {
        "description": "Brede bevestiging: olie, tankers, goud, energie-aandelen en volatiliteit lopen op.",
    },
    "Inflation Stress": {
        "description": "Olie, rente en dollar wijzen samen op oplopende inflatiedruk.",
    },
}


@st.cache_data(ttl=900)
def load_prices(tickers, period="6mo"):
    raw = yf.download(
        list(tickers.values()),
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )

    data = pd.DataFrame()

    for name, ticker in tickers.items():
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                data[name] = raw[ticker]["Close"]
            else:
                data[name] = raw["Close"]
        except Exception:
            data[name] = np.nan

    return data.dropna(how="all")


def pct_change(df, days=5):
    if len(df) <= days:
        return pd.Series(index=df.columns, dtype=float)

    return (df.iloc[-1] / df.iloc[-days] - 1) * 100


def score_signal(value, bullish=True):
    if pd.isna(value):
        return 0

    raw = min(max(value, -2), 2) / 2
    return raw if bullish else -raw


def normalized_chart(data, selected_assets, title, height=420):
    valid_assets = [
        asset for asset in selected_assets
        if asset in data.columns and data[asset].dropna().shape[0] > 5
    ]

    if not valid_assets:
        st.warning(f"Geen geldige data beschikbaar voor {title}")
        return

    clean = data[valid_assets].ffill().dropna(how="all")
    normalized = clean / clean.iloc[0] * 100

    fig = go.Figure()

    for col in normalized.columns:
        fig.add_trace(
            go.Scatter(
                x=normalized.index,
                y=normalized[col],
                mode="lines",
                name=col,
                line=dict(width=2),
            )
        )

    fig.update_layout(
        height=height,
        title=title,
        yaxis_title="Geïndexeerd naar 100",
        hovermode="x unified",
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.02,
        ),
        margin=dict(l=20, r=90, t=60, b=40),
    )

    st.plotly_chart(fig, use_container_width=True)


prices = load_prices(TICKERS)

if prices.empty:
    st.error("Geen marktdata geladen. Controleer ticker-symbolen of yfinance beschikbaarheid.")
    st.stop()

prices = prices.ffill()

latest = prices.iloc[-1]
weekly = pct_change(prices, 5)

xle_spy_ratio = prices["XLE"] / prices["SPY"]
xle_spy_5d = (xle_spy_ratio.iloc[-1] / xle_spy_ratio.iloc[-5] - 1) * 100

tanker_mom = np.nanmean(
    [
        weekly.get("Frontline", np.nan),
        weekly.get("International Seaways", np.nan),
    ]
)

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
    1,
)

regime_score = max(0, min(100, regime_score))


silent_accumulation = (
    abs(brent_mom) < 2
    and xle_spy_5d > 1
    and tanker_mom > 2
)

fake_headline = (
    brent_mom > 4
    and xle_spy_5d < 0
    and tanker_mom < 1
)

hidden_supply_stress = (
    brent_mom > 2
    and tanker_mom > 3
    and ovx_mom > 3
)

real_crisis = (
    brent_mom > 3
    and xle_spy_5d > 1
    and tanker_mom > 3
    and gold_mom > 1
    and ovx_mom > 3
)

inflation_stress = (
    brent_mom > 2
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


st.title("RetailTraders.nl | Oil Geopolitics Dashboard")
st.caption("Focus: OPEC fracture risk, oil structure, energy equities, tankers, volatiliteit en inflatiestress.")

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
    st.subheader("Market Structure")

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "Oil & Gold",
            "Energy Equities",
            "Volatility",
            "XLE vs SPY",
        ]
    )

    with tab1:
        normalized_chart(
            prices,
            ["Brent", "WTI", "Gold", "DXY"],
            "Oil, Gold & Dollar",
        )

    with tab2:
        normalized_chart(
            prices,
            ["XLE", "Exxon", "Shell", "Frontline", "International Seaways"],
            "Energy Equities & Tankers",
        )

    with tab3:
        normalized_chart(
            prices,
            ["OVX", "VIX"],
            "Oil Volatility vs Equity Volatility",
        )

    with tab4:
        ratio_fig = go.Figure()

        ratio_fig.add_trace(
            go.Scatter(
                x=xle_spy_ratio.index,
                y=xle_spy_ratio,
                mode="lines",
                name="XLE / SPY",
                line=dict(width=2),
            )
        )

        ratio_fig.update_layout(
            height=420,
            title="Energy Sector Relative Strength vs S&P 500",
            yaxis_title="XLE / SPY Ratio",
            hovermode="x unified",
            margin=dict(l=20, r=40, t=60, b=40),
        )

        st.plotly_chart(ratio_fig, use_container_width=True)

with right:
    st.subheader("Signal Engine")

    for name, active in signals.items():
        if active:
            st.error(f"ACTIVE: {name}")
            st.caption(ALERT_THRESHOLDS[name]["description"])
        else:
            st.success(f"Neutral: {name}")

    st.divider()
    st.caption("Discord alerts: uitgevoerd via GitHub Actions")


st.divider()

st.subheader("Latest Market Snapshot")

snapshot = pd.DataFrame(
    {
        "Laatste waarde": latest,
        "5D %": weekly,
    }
).round(2)

st.dataframe(snapshot, use_container_width=True)

st.divider()

st.subheader("Data Quality Check")

data_quality = pd.DataFrame(
    {
        "Ticker Name": prices.columns,
        "Data Points": [prices[col].dropna().shape[0] for col in prices.columns],
        "Latest Value": [
            prices[col].dropna().iloc[-1]
            if prices[col].dropna().shape[0] > 0
            else np.nan
            for col in prices.columns
        ],
        "Missing %": [(prices[col].isna().mean() * 100) for col in prices.columns],
    }
).round(2)

st.dataframe(data_quality, use_container_width=True)