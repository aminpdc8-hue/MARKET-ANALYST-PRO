import os
import time
import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from matplotlib.patches import Rectangle


# ================= CONFIG =================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

BINANCE_URL = "https://data-api.binance.vision"

SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
}

INTERVAL = "12h"
LIMIT = 100


# ================= DATA =================

def get_binance_data(symbol):

    url = f"{BINANCE_URL}/api/v3/klines"

    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "limit": LIMIT
    }

    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()

    data = response.json()

    df = pd.DataFrame(data, columns=[
        "time", "open", "high", "low",
        "close", "volume", "close_time",
        "quote_volume", "trades",
        "buy_volume", "buy_quote", "ignore"
    ])

    df["time"] = pd.to_datetime(df["time"], unit="ms")

    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)

    return df[["time", "open", "high", "low", "close"]]


# ================= YAHOO FALLBACK =================

def get_yahoo_data(symbol):

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    params = {
        "range": "60d",
        "interval": "1h"
    }

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=20
    )

    response.raise_for_status()

    result = response.json()["chart"]["result"][0]

    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]

    df = pd.DataFrame({
        "time": pd.to_datetime(timestamps, unit="s"),
        "open": quote["open"],
        "high": quote["high"],
        "low": quote["low"],
        "close": quote["close"]
    })

    df = df.dropna()

    df["time"] = pd.to_datetime(df["time"], utc=True)
    df["time"] = df["time"].dt.tz_convert(None)

    df = df.set_index("time")

    df = df.resample("12h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last"
    }).dropna().reset_index()

    return df.tail(LIMIT)


# ================= GOLD =================

def get_gold_data():

    errors = []

    for symbol in ["XAUUSD=X", "GC=F"]:

        try:
            df = get_yahoo_data(symbol)

            if len(df) >= 30:
                print(f"GOLD SOURCE: {symbol}")
                return df

        except Exception as e:
            errors.append(f"{symbol}: {e}")
            print("Gold source error:", symbol, e)

    raise Exception("Gold data unavailable: " + str(errors))


# ================= SUPPORT / RESISTANCE =================

def find_zones(df):

    supports = []
    resistances = []

    highs = df["high"].values
    lows = df["low"].values

    for i in range(3, len(df) - 3):

        if highs[i] == max(highs[i-3:i+4]):
            resistances.append(highs[i])

        if lows[i] == min(lows[i-3:i+4]):
            supports.append(lows[i])

    price = df["close"].iloc[-1]

    supports = [
        x for x in supports if x < price
    ]

    resistances = [
        x for x in resistances if x > price
    ]

    supports = sorted(supports, reverse=True)[:4]
    resistances = sorted(resistances)[:4]

    return supports, resistances


# ================= CHART =================

def create_chart(name, df):

    fig, ax = plt.subplots(figsize=(15, 8))

    dates = mdates.date2num(df["time"])

    candle_width = 0.35

    for i, row in df.iterrows():

        color = (
    "#006400"  # سبز تیره
    if row["close"] >= row["open"]
    else "#D8B4FE"  # بنفش کم‌رنگ
)

        ax.plot(
            [dates[i], dates[i]],
            [row["low"], row["high"]],
            color=color,
            linewidth=1.2
        )

        body_height = abs(row["close"] - row["open"])

        if body_height == 0:
            body_height = 0.0001

        rect = Rectangle(
            (dates[i] - candle_width / 2,
             min(row["open"], row["close"])),
            candle_width,
            body_height,
            facecolor=color,
            edgecolor=color
        )

        ax.add_patch(rect)

    supports, resistances = find_zones(df)

    current_price = df["close"].iloc[-1]

    zone_width = current_price * 0.0015

    # SUPPORT ZONES

    for level in supports:

        ax.axhspan(
            level - zone_width,
            level + zone_width,
            color="green",
            alpha=0.18
        )

    # RESISTANCE ZONES

    for level in resistances:

        ax.axhspan(
            level - zone_width,
            level + zone_width,
            color="red",
            alpha=0.18
        )

    ax.set_title(
        f"{name} / USDT - 12H",
        fontsize=17
    )

    ax.grid(alpha=0.15)

    ax.xaxis_date()

    ax.xaxis.set_major_formatter(
        mdates.DateFormatter("%m-%d")
    )

    ax.set_xlim(
        dates[0] - 1,
        dates[-1] + 2
    )

    plt.tight_layout()

    filename = f"/tmp/{name}_12H.png"

    plt.savefig(
        filename,
        dpi=150,
        bbox_inches="tight"
    )

    plt.close()

    return filename


# ================= TELEGRAM =================

def send_photo(filename, caption):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    with open(filename, "rb") as photo:

        response = requests.post(
            url,
            data={
                "chat_id": CHANNEL_ID,
                "caption": caption
            },
            files={
                "photo": photo
            },
            timeout=40
        )

    response.raise_for_status()

    if not response.json().get("ok"):
        raise Exception(response.text)


# ================= ANALYSIS =================

def analyze(name, symbol):

    print("Analyzing", name)

    try:

        df = get_binance_data(symbol)

    except Exception as e:

        print("Binance error:", name, e)

        yahoo_symbols = {
            "BTC": "BTC-USD",
            "ETH": "ETH-USD"
        }

        df = get_yahoo_data(yahoo_symbols[name])

    if len(df) < 30:
        raise Exception("Not enough candle data")

    filename = create_chart(name, df)

    price = df["close"].iloc[-1]

    supports, resistances = find_zones(df)

    caption = (
        f"📊 {name} / USDT\n"
        f"⏱ Timeframe: 12H\n"
        f"💰 Price: {price:,.4f}\n"
        f"🟢 Support zones: {len(supports)}\n"
        f"🔴 Resistance zones: {len(resistances)}\n"
        f"📈 Technical Market Chart"
    )

    send_photo(filename, caption)

    print("SUCCESS:", name)


# ================= MAIN =================

def main():

    if not BOT_TOKEN or not CHANNEL_ID:
        raise Exception("Telegram credentials missing")

    for name, symbol in SYMBOLS.items():

        try:
            analyze(name, symbol)

        except Exception as e:
            print(f"ERROR {name}: {e}")

        time.sleep(3)

    try:

        print("Analyzing XAU")

        df = get_gold_data()

        filename = create_chart("XAU", df)

        price = df["close"].iloc[-1]

        caption = (
            f"🥇 GOLD / XAUUSD\n"
            f"⏱ Timeframe: 12H\n"
            f"💰 Price: {price:,.2f}\n"
            f"📈 Technical Market Chart"
        )

        send_photo(filename, caption)

        print("SUCCESS: XAU")

    except Exception as e:

        print("ERROR XAU:", e)


if __name__ == "__main__":
    main()
