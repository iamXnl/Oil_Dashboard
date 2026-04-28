import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import requests
from datetime import datetime, timezone

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
    "OVX": "^OVX",
    "Gold": "GC=F",
    "VIX": "^VIX",
    "DXY": "DX-Y.NYB",
    "US 10Y Yield": "^TNX",
}

ALERT_THRESHOLDS = {
    "Silent Accumulation": {
        "description": "Brent vlak, maar energie-aandelen en tankers lopen op. Mogelijke institutionele positionering.",
        "severity": "opportunity",
    },
    "Fake Headline Move": {
        "description": "Brent stijgt hard, maar aandelen en tankers bevestigen niet. Kans op emotionele headline move.",
        "severity": "warning",
    },
    "Hidden Supply Stress": {
        "description": "Brent, tankers en olievolatiliteit stijgen tegelijk. Mogelijke fysieke marktstress.",
        "severity": "warning",
    },
    "Real Crisis Mode": {
        "description": "Brede bevestiging: olie, tankers, goud, energie-aandelen en volatiliteit lopen op.",
        "severity": "critical",
    },
    "Inflation Stress": {
        "description": "Olie, rente en dollar wijzen samen op inflatiedruk.",
        "severity": "macro",
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
        fig.add_trace(go.Scatter(
            x=normalized.index,
            y=normalized[col],
            mode="lines",
            name=col,
            line=dict(width=2)
        ))

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
            x=1.02
        ),
        margin=dict(l=20, r=90, t=60, b=40)
    )

    st.plotly_chart(fig, use_container_width=True)


def get_discord_webhook_url():
    try:
        return st.secrets["DISCORD_WEBHOOK_URL"]
    except Exception:
        return None


def build_discord_message(active_signals, metrics):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "🚨 **RetailTraders Oil Dashboard Alert**",
        "",
        f"**Tijd:** {timestamp}",
        "",
        "**Actieve signalen:**"
    ]

    for signal_name in active_signals:
        meta = ALERT_THRESHOLDS.get(signal_name, {})
        lines.append(f"- **{signal_name}**: {meta.get('description', '')}")

    lines.extend([
        "",
        "**Marktdata 5D:**",
        f"- Brent: {metrics['brent_mom']:.2f}%",
        f"- XLE vs SPY: {metrics['xle_spy_5d']:.2f}%",
        f"- Tanker Basket: {metrics['tanker_mom']:.2f}%",
        f"- OVX: {metrics['ovx_mom']:.2f}%",
        f"- VIX: {metrics['vix_mom']:.2f}%",
        f"- Gold: {metrics['gold_mom']:.2f}%",
        f"- DXY: {metrics['dxy_mom']:.2f}%",
        f"- US 10Y Yield: {metrics['yield_mom']:.2f}%",
        "",
        "**Interpretatie:** Dit is een kwantitatief waarschuwingssignaal, geen automatisch koop- of verkoopsignaal."
        "",
        "**Check Dashboard: https://retailtraders.streamlit.app/ "
    ])

    return "\n".join(lines)


def send_discord_alert(active_signals, metrics):"",
    webhook_url = get_discord_webhook_url()

    if not webhook_url:
        return False, "Geen Discord webhook ingesteld in Streamlit Secrets."

    message = build_discord_message(active_signals, metrics)

    payload = {
        "username": "RetailTraders Oil Monitor",
        "content": message
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)

        if response.status_code in [200, 204]:
            return True, "Discord alert verzonden."
        return False, f"Discord fout: HTTP {response.status_code} - {response.text}"

    except Exception as e:
        return False, f"Discord request mislukt: {e}"


def get_alert_key(active_signals, metrics):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    signal_part = "|".join(sorted(active_signals))
    metric_part = round(metrics["regime_score"], 1)
    return f"{today}:{signal_part}:{metric_part}"


prices = load_prices(TICKERS)

if prices.empty:
    st.error("Geen marktdata geladen. Controleer ticker-symbolen of yfinance beschikbaarheid.")
    st.stop()

prices = prices.ffill()

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

metrics = {
    "regime_score": regime_score,
    "brent_mom": brent_mom,
    "xle_spy_5d": xle_spy_5d,
    "tanker_mom": tanker_mom,
    "ovx_mom": ovx_mom,
    "vix_mom": vix_mom,
    "gold_mom": gold_mom,
    "dxy_mom": dxy_mom,
    "yield_mom": yield_mom,
}

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

active_signals = [name for name, active in signals.items() if active]

st.title("RetailTraders.nl - Oil Geopolitics Signal Dashboard")
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

    tab1, tab2, tab3, tab4 = st.tabs([
        "Oil & Gold",
        "Energy Equities",
        "Volatility",
        "XLE vs SPY"
    ])

    with tab1:
        normalized_chart(
            prices,
            ["Brent", "WTI", "Gold", "DXY"],
            "Oil, Gold & Dollar"
        )

    with tab2:
        normalized_chart(
            prices,
            ["XLE", "Exxon", "Shell", "Frontline", "International Seaways"],
            "Energy Equities & Tankers"
        )

    with tab3:
        normalized_chart(
            prices,
            ["OVX", "VIX"],
            "Oil Volatility vs Equity Volatility"
        )

    with tab4:
        ratio_fig = go.Figure()

        ratio_fig.add_trace(go.Scatter(
            x=xle_spy_ratio.index,
            y=xle_spy_ratio,
            mode="lines",
            name="XLE / SPY",
            line=dict(width=2)
        ))

        ratio_fig.update_layout(
            height=420,
            title="Energy Sector Relative Strength vs S&P 500",
            yaxis_title="XLE / SPY Ratio",
            hovermode="x unified",
            margin=dict(l=20, r=40, t=60, b=40)
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
    st.subheader("Discord Alerts")

    webhook_configured = get_discord_webhook_url() is not None

    if webhook_configured:
        st.success("Discord webhook is ingesteld.")
    else:
        st.warning("Geen Discord webhook gevonden in Streamlit Secrets.")

    auto_alerts_enabled = st.toggle(
        "Automatische Discord alerts aan",
        value=True
    )

    if active_signals:
        st.warning(f"Actieve signalen: {', '.join(active_signals)}")

        alert_key = get_alert_key(active_signals, metrics)

        if "last_discord_alert_key" not in st.session_state:
            st.session_state["last_discord_alert_key"] = None

        if auto_alerts_enabled and st.session_state["last_discord_alert_key"] != alert_key:
            ok, msg = send_discord_alert(active_signals, metrics)

            if ok:
                st.session_state["last_discord_alert_key"] = alert_key
                st.success(msg)
            else:
                st.warning(msg)

        if st.button("Verstuur test/handmatige Discord alert"):
            ok, msg = send_discord_alert(active_signals, metrics)
            if ok:
                st.success(msg)
            else:
                st.warning(msg)
    else:
        st.info("Geen actieve signalen. Er wordt geen Discord alert verstuurd.")

        if st.button("Verstuur Discord testbericht"):
            test_signals = ["Test Alert"]
            test_metrics = metrics.copy()
            webhook_url = get_discord_webhook_url()

            if not webhook_url:
                st.warning("Geen Discord webhook ingesteld.")
            else:
                payload = {
                    "username": "RetailTraders Oil Monitor",
                    "content": (
                        "✅ **RetailTraders Oil Dashboard Testbericht**\n\n"
                        "De Discord webhook werkt correct.\n\n"
                        "Taal: Nederlands\n"
                        "Status: operationeel"
                    )
                }

                try:
                    response = requests.post(webhook_url, json=payload, timeout=10)
                    if response.status_code in [200, 204]:
                        st.success("Testbericht verzonden.")
                    else:
                        st.warning(f"Discord fout: HTTP {response.status_code} - {response.text}")
                except Exception as e:
                    st.warning(f"Discord request mislukt: {e}")

st.divider()

st.subheader("Latest Market Snapshot")

snapshot = pd.DataFrame({
    "Laatste waarde": latest,
    "5D %": weekly
}).round(2)

st.dataframe(snapshot, use_container_width=True)

st.divider()

st.subheader("Data Quality Check")

data_quality = pd.DataFrame({
    "Ticker Name": prices.columns,
    "Data Points": [prices[col].dropna().shape[0] for col in prices.columns],
    "Latest Value": [
        prices[col].dropna().iloc[-1] if prices[col].dropna().shape[0] > 0 else np.nan
        for col in prices.columns
    ],
    "Missing %": [(prices[col].isna().mean() * 100) for col in prices.columns],
}).round(2)

st.dataframe(data_quality, use_container_width=True)