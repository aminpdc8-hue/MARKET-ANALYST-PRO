import os
import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
from datetime import datetime, timezone

# ================= CONFIG =================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

BINANCE_URL = "https://api.binance.com/api/v3/klines"

CHARTS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT"
}

TIMEFRAME = "12h"
CANDLES = 100

# ================= TELEGRAM =================

def telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    r = requests.post(
        url,
        data={"chat_id": CHANNEL_ID, "text": message},
        timeout=30
    )
    r.raise_for_status()


def telegram_photo(path, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    with open(path, "rb") as photo:
        r = requests.post(
            url,
            data={
                "chat_id": CHANNEL_ID,
                "caption": caption
            },
            files={"photo": photo},
            timeout=60
        )

    r.raise_for_status()


# ================= MARKET DATA =================

def get_binance_data(symbol):

    r = requests.get(
        BINANCE_URL,
        params={
            "symbol": symbol,
            "interval": TIMEFRAME,
            "limit": CANDLES
        },
        timeout=30
    )

    r.raise_for_status()

    rows = r.json()

    df = pd.DataFrame(rows, columns=[
        "time", "open", "high", "low", "close",
        "volume", "close_time", "quote_volume",
        "trades", "taker_buy", "taker_quote", "ignore"
    ])

    df["time"] = pd.to_datetime(df["time"], unit="ms")

    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col])

    return df[["time", "open", "high", "low", "close"]]


def get_gold_data():

    tickers = ["XAUUSD=X", "GC=F"]

    for ticker in tickers:

        try:
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/"
                f"{ticker}?range=60d&interval=1h"
            )

            r = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=30
            )

            r.raise_for_status()

            result = r.json()["chart"]["result"][0]

            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]

            df = pd.DataFrame({
                "time": pd.to_datetime(
                    timestamps, unit="s", utc=True
                ).tz_convert(None),
                "open": quote["open"],
                "high": quote["high"],
                "low": quote["low"],
                "close": quote["close"]
            })

            df = df.dropna()

            df = df.set_index("time").resample("12h").agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last"
            }).dropna().reset_index()

            if len(df) >= 20:
                return df.tail(CANDLES)

        except Exception as e:
            print(f"Gold source error {ticker}: {e}")

    raise RuntimeError("Gold market data unavailable")


# ================= SUPPORT / RESISTANCE =================

def find_zones(df):

    high = df["high"].tolist()
    low = df["low"].tolist()

    atr = (
        df["high"] - df["low"]
    ).rolling(14).mean().iloc[-1]

    if pd.isna(atr) or atr <= 0:
        atr = df["close"].iloc[-1] * 0.005

    supports = []
    resistances = []

    for i in range(3, len(df) - 3):

        # Pivot Low
        if low[i] == min(low[i-3:i+4]):
            supports.append(low[i])

        # Pivot High
        if high[i] == max(high[i-3:i+4]):
            resistances.append(high[i])

    def cluster_levels(levels):

        zones = []

        for price in sorted(levels):

            matched = False

            for zone in zones:

                if abs(price - zone["price"]) <= atr * 0.5:

                    zone["prices"].append(price)
                    zone["price"] = sum(
                        zone["prices"]
                    ) / len(zone["prices"])

                    matched = True
                    break

            if not matched:
                zones.append({
                    "price": price,
                    "prices": [price]
                })

        zones.sort(
            key=lambda x: len(x["prices"]),
            reverse=True
        )

        return zones[:4]

    return (
        cluster_levels(supports),
        cluster_levels(resistances),
        atr
    )


# ================= DRAW CHART =================

def create_chart(name, df):

    supports, resistances, atr = find_zones(df)

    fig, ax = plt.subplots(figsize=(15, 9))

    fig.patch.set_facecolor("#131722")
    ax.set_facecolor("#131722")

    width = 0.35

    for i, row in df.iterrows():

        x = mdates.date2num(row["time"])

        color = (
            "#26a69a"
            if row["close"] >= row["open"]
            else "#ef5350"
        )

        ax.plot(
            [x, x],
            [row["low"], row["high"]],
            color=color,
            linewidth=1
        )

        bottom = min(row["open"], row["close"])
        height = abs(row["close"] - row["open"])

        if height == 0:
            height = atr * 0.015

        candle = Rectangle(
            (x - width / 2, bottom),
            width,
            height,
            facecolor=color,
            edgecolor=color
        )

        ax.add_patch(candle)

    # Support zones
    for zone in supports:

        price = zone["price"]

        ax.axhspan(
            price - atr * 0.20,
            price + atr * 0.20,
            color="#00c853",
            alpha=0.20
        )

        ax.axhline(
            price,
            color="#00e676",
            linewidth=1,
            linestyle="--"
        )

    # Resistance zones
    for zone in resistances:

        price = zone["price"]

        ax.axhspan(
            price - atr * 0.20,
            price + atr * 0.20,
            color="#ff1744",
            alpha=0.20
        )

        ax.axhline(
            price,
            color="#ff5252",
            linewidth=1,
            linestyle="--"
        )

    current_price = df["close"].iloc[-1]

    ax.axhline(
        current_price,
        color="white",
        linestyle=":",
        linewidth=1
    )

    ax.set_title(
        f"{name} | 12H MARKET ANALYSIS",
        color="white",
        fontsize=18,
        pad=20
    )

    ax.xaxis.set_major_formatter(
        mdates.DateFormatter("%m-%d")
    )

    ax.tick_params(colors="white")

    for spine in ax.spines.values():
        spine.set_color("#555555")

    ax.grid(
        alpha=0.15,
        color="white"
    )

    ax.set_xlim(
        mdates.date2num(df["time"].iloc[0]) - 1,
        mdates.date2num(df["time"].iloc[-1]) + 1
    )

    plt.tight_layout()

    path = f"/tmp/{name}_12H.png"

    plt.savefig(
        path,
        dpi=150,
        facecolor=fig.get_facecolor()
    )

    plt.close(fig)

    return path, supports, resistances, current_price


# ================= MAIN =================

def main():

    if not BOT_TOKEN or not CHANNEL_ID:
        raise RuntimeError("Telegram secrets missing")

    telegram_message(
        "📊 MARKET ANALYST PRO\n"
        "شروع تحلیل بازار\n"
        "⏱ تایم‌فریم: 12H\n"
        "🟢 حمایت: Support Zones\n"
        "🔴 مقاومت: Resistance Zones"
    )

    markets = {
        "BTC": lambda: get_binance_data("BTCUSDT"),
        "ETH": lambda: get_binance_data("ETHUSDT"),
        "XAU": get_gold_data
    }

    for name, fetch in markets.items():

        try:

            print(f"Analyzing {name}")

            df = fetch()

            path, supports, resistances, price = create_chart(
                name, df
            )

            caption = (
                f"📊 {name} | 12H\n"
                f"💰 Current Price: {price:,.4f}\n"
                f"🟢 Support Zones: {len(supports)}\n"
                f"🔴 Resistance Zones: {len(resistances)}\n"
                f"🕒 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
            )

            telegram_photo(path, caption)

            print(f"SUCCESS: {name}")

        except Exception as e:

            print(f"ERROR {name}: {e}")

            telegram_message(
                f"⚠️ Error analyzing {name}\n{str(e)[:500]}"
            )

    telegram_message(
        "✅ MARKET ANALYST PRO\n"
        "گزارش بازار به پایان رسید."
    )


if __name__ == "__main__":
    main()
