import os
import json
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timezone, timedelta

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

ALERT_STATE_FILE = "discord_alert_state.json"
ALERT_COOLDOWN_HOURS = 12

ALERT_DESCRIPTIONS = {
    "Silent Accumulation": "Brent beweegt beperkt, maar energie-aandelen en tankers lopen op. Mogelijke institutionele positionering.",
    "Fake Headline Move": "Brent stijgt hard, maar energie-aandelen en tankers bevestigen niet. Kans op emotionele headline move.",
    "Hidden Supply Stress": "Brent, tankers en olievolatiliteit stijgen tegelijk. Mogelijke fysieke marktstress.",
    "Real Crisis Mode": "Brede bevestiging: olie, tankers, goud, energie-aandelen en volatiliteit lopen op.",
    "Inflation Stress": "Olie, rente en dollar wijzen samen op oplopende inflatiedruk.",
}


def load_prices(period="6mo"):
    raw = yf.download(
        list(TICKERS.values()),
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )

    data = pd.DataFrame()

    for name, ticker in TICKERS.items():
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                data[name] = raw[ticker]["Close"]
            else:
                data[name] = raw["Close"]
        except Exception:
            data[name] = np.nan

    return data.dropna(how="all").ffill()


def pct_change(df, days=5):
    if len(df) <= days:
        return pd.Series(index=df.columns, dtype=float)
    return (df.iloc[-1] / df.iloc[-days] - 1) * 100


def score_signal(value, bullish=True):
    if pd.isna(value):
        return 0
    raw = min(max(value, -2), 2) / 2
    return raw if bullish else -raw


def load_alert_state():
    if not os.path.exists(ALERT_STATE_FILE):
        return {}

    try:
        with open(ALERT_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_alert_state(state):
    with open(ALERT_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def get_alert_key(active_signals):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    signal_part = "|".join(sorted(active_signals))
    return f"{today}:{signal_part}"


def should_send_alert(alert_key):
    state = load_alert_state()
    now = datetime.now(timezone.utc)

    last_sent_raw = state.get(alert_key)

    if not last_sent_raw:
        return True

    try:
        last_sent = datetime.fromisoformat(last_sent_raw)
        hours_since = (now - last_sent).total_seconds() / 3600
        return hours_since >= ALERT_COOLDOWN_HOURS
    except Exception:
        return True


def mark_alert_sent(alert_key):
    state = load_alert_state()
    state[alert_key] = datetime.now(timezone.utc).isoformat()
    save_alert_state(state)


def build_discord_message(active_signals, metrics):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "🚨 **RetailTraders Oil Dashboard Alert**",
        "",
        f"**Tijd:** {timestamp}",
        "",
        "**Actieve signalen:**",
    ]

    for signal in active_signals:
        lines.append(f"- **{signal}**: {ALERT_DESCRIPTIONS.get(signal, '')}")

    lines.extend([
        "",
        "**Marktdata 5D:**",
        f"- Oil Geopolitics Score: {metrics['regime_score']:.1f}",
        f"- Brent: {metrics['brent_mom']:.2f}%",
        f"- XLE vs SPY: {metrics['xle_spy_5d']:.2f}%",
        f"- Tanker Basket: {metrics['tanker_mom']:.2f}%",
        f"- OVX: {metrics['ovx_mom']:.2f}%",
        f"- VIX: {metrics['vix_mom']:.2f}%",
        f"- Gold: {metrics['gold_mom']:.2f}%",
        f"- DXY: {metrics['dxy_mom']:.2f}%",
        f"- US 10Y Yield: {metrics['yield_mom']:.2f}%",
        "",
        "**Interpretatie:** Dit is een kwantitatief waarschuwingssignaal, geen automatisch koop- of verkoopsignaal. Check https://retailtraders.streamlit.app/",
    ])

    return "\n".join(lines)


def send_discord_alert(active_signals, metrics):
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        print("DISCORD_WEBHOOK_URL ontbreekt.")
        return False

    payload = {
        "username": "RetailTraders Oil Monitor",
        "content": build_discord_message(active_signals, metrics),
    }

    response = requests.post(webhook_url, json=payload, timeout=15)

    if response.status_code in [200, 204]:
        print("Discord alert verzonden.")
        return True

    print(f"Discord fout: HTTP {response.status_code} - {response.text}")
    return False


def main():
    prices = load_prices()

    if prices.empty:
        raise RuntimeError("Geen marktdata geladen.")

    weekly = pct_change(prices, 5)

    xle_spy_ratio = prices["XLE"] / prices["SPY"]
    xle_spy_5d = (xle_spy_ratio.iloc[-1] / xle_spy_ratio.iloc[-5] - 1) * 100

    tanker_mom = np.nanmean([
        weekly.get("Frontline", np.nan),
        weekly.get("International Seaways", np.nan),
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
        1,
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

    signals = {
        "Silent Accumulation": (
            abs(brent_mom) < 2
            and xle_spy_5d > 1
            and tanker_mom > 2
        ),
        "Fake Headline Move": (
            brent_mom > 4
            and xle_spy_5d < 0
            and tanker_mom < 1
        ),
        "Hidden Supply Stress": (
            brent_mom > 2
            and tanker_mom > 3
            and ovx_mom > 3
        ),
        "Real Crisis Mode": (
            brent_mom > 3
            and xle_spy_5d > 1
            and tanker_mom > 3
            and gold_mom > 1
            and ovx_mom > 3
        ),
        "Inflation Stress": (
            brent_mom > 2
            and yield_mom > 1
            and dxy_mom > 0
        ),
    }

    active_signals = [name for name, active in signals.items() if active]

    print(f"Actieve signalen: {active_signals if active_signals else 'geen'}")

    if not active_signals:
        return

    alert_key = get_alert_key(active_signals)

    if should_send_alert(alert_key):
        sent = send_discord_alert(active_signals, metrics)

        if sent:
            mark_alert_sent(alert_key)
    else:
        print("Alert overgeslagen: cooldown actief.")


if __name__ == "__main__":
    main()