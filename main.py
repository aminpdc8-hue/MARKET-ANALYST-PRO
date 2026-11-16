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
    "ETH": "ETHUSDT"
}

LIMIT_12H = 100
LIMIT_1H = 120

GREEN = "#006400"
PURPLE = "#D8B4FE"


# ================= BINANCE DATA =================

def get_binance_data(symbol, interval, limit):

    url = f"{BINANCE_URL}/api/v3/klines"

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    response = requests.get(
        url,
        params=params,
        timeout=25
    )

    response.raise_for_status()

    data = response.json()

    df = pd.DataFrame(data, columns=[
        "time", "open", "high", "low",
        "close", "volume", "close_time",
        "quote_volume", "trades",
        "buy_volume", "buy_quote", "ignore"
    ])

    df["time"] = pd.to_datetime(
        df["time"], unit="ms"
    )

    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)

    return df[[
        "time", "open", "high", "low", "close"
    ]]


# ================= YAHOO DATA =================

def get_yahoo_data(symbol, interval, period):

    url = (
        f"https://query1.finance.yahoo.com/"
        f"v8/finance/chart/{symbol}"
    )

    params = {
        "range": period,
        "interval": interval
    }

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=25
    )

    response.raise_for_status()

    result = response.json()["chart"]["result"][0]

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

    return df.dropna().reset_index(drop=True)


# ================= GOLD DATA =================

def get_gold_data(interval):

    errors = []

    for symbol in ["XAUUSD=X", "GC=F"]:

        try:

            period = "60d" if interval == "1h" else "730d"

            df = get_yahoo_data(
                symbol,
                interval,
                period
            )

            if len(df) >= 30:

                print("GOLD SOURCE:", symbol)

                return df.tail(
                    LIMIT_1H if interval == "1h"
                    else LIMIT_12H
                )

        except Exception as e:

            print("GOLD ERROR:", symbol, e)

            errors.append(str(e))

    raise Exception(str(errors))


# ================= MARKET DATA =================

def get_market_data(name, interval):

    if name == "XAU":

        return get_gold_data(interval)

    limit = (
        LIMIT_12H
        if interval == "12h"
        else LIMIT_1H
    )

    try:

        return get_binance_data(
            SYMBOLS[name],
            interval,
            limit
        )

    except Exception as e:

        print("BINANCE ERROR:", name, interval, e)

        yahoo_symbol = {
            "BTC": "BTC-USD",
            "ETH": "ETH-USD"
        }

        period = (
            "730d"
            if interval == "12h"
            else "60d"
        )

        return get_yahoo_data(
            yahoo_symbol[name],
            interval,
            period
        ).tail(limit)


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

    supports = sorted(
        [x for x in supports if x < price],
        reverse=True
    )[:4]

    resistances = sorted(
        [x for x in resistances if x > price]
    )[:4]

    return supports, resistances


# ================= ORDER BLOCK =================

def find_order_blocks(df):

    blocks = []

    for i in range(5, len(df) - 1):

        row = df.iloc[i]

        previous = df.iloc[max(0, i-5):i]

        body = abs(row["close"] - row["open"])

        avg_body = (
            previous["close"] - previous["open"]
        ).abs().mean()

        if avg_body == 0:
            continue

        # Bullish displacement

        if (
            row["close"] > row["open"]
            and body > avg_body * 1.5
            and row["close"] > previous["high"].max()
        ):

            for j in range(i-1, max(-1, i-6), -1):

                candle = df.iloc[j]

                if candle["close"] < candle["open"]:

                    blocks.append({
                        "type": "bullish",
                        "low": candle["low"],
                        "high": candle["high"],
                        "time": candle["time"]
                    })

                    break

        # Bearish displacement

        elif (
            row["close"] < row["open"]
            and body > avg_body * 1.5
            and row["close"] < previous["low"].min()
        ):

            for j in range(i-1, max(-1, i-6), -1):

                candle = df.iloc[j]

                if candle["close"] > candle["open"]:

                    blocks.append({
                        "type": "bearish",
                        "low": candle["low"],
                        "high": candle["high"],
                        "time": candle["time"]
                    })

                    break

    return blocks[-5:]


# ================= FAIR VALUE GAP =================

def find_fvg(df):

    gaps = []

    for i in range(2, len(df)):

        first = df.iloc[i-2]
        third = df.iloc[i]

        # Bullish FVG

        if third["low"] > first["high"]:

            gaps.append({
                "type": "bullish",
                "low": first["high"],
                "high": third["low"],
                "time": third["time"]
            })

        # Bearish FVG

        elif third["high"] < first["low"]:

            gaps.append({
                "type": "bearish",
                "low": third["high"],
                "high": first["low"],
                "time": third["time"]
            })

    return gaps[-6:]


# ================= CANDLE DRAWING =================

def draw_candles(ax, df, interval):

    dates = mdates.date2num(df["time"])

    width = 0.35 if interval == "12h" else 0.025

    for i, row in enumerate(df.itertuples()):

        color = (
            GREEN
            if row.close >= row.open
            else PURPLE
        )

        ax.plot(
            [dates[i], dates[i]],
            [row.low, row.high],
            color=color,
            linewidth=1
        )

        height = abs(row.close - row.open)

        if height == 0:
            height = 0.000001

        rect = Rectangle(
            (
                dates[i] - width / 2,
                min(row.open, row.close)
            ),
            width,
            height,
            facecolor=color,
            edgecolor=color
        )

        ax.add_patch(rect)

    ax.grid(alpha=0.15)

    ax.xaxis_date()

    ax.xaxis.set_major_formatter(
        mdates.DateFormatter("%m-%d %H:%M")
    )


# ================= DRAW OB =================

def draw_order_blocks(ax, df):

    blocks = find_order_blocks(df)

    last_date = mdates.date2num(
        df["time"].iloc[-1]
    )

    for block in blocks:

        color = (
            "#00A86B"
            if block["type"] == "bullish"
            else "#E53935"
        )

        start = mdates.date2num(block["time"])

        ax.add_patch(
            Rectangle(
                (start, block["low"]),
                last_date - start + 0.08,
                block["high"] - block["low"],
                facecolor=color,
                edgecolor=color,
                alpha=0.18,
                linewidth=1.2
            )
        )


# ================= DRAW FVG =================

def draw_fvg(ax, df):

    gaps = find_fvg(df)

    last_date = mdates.date2num(
        df["time"].iloc[-1]
    )

    for gap in gaps:

        color = (
            "#00C853"
            if gap["type"] == "bullish"
            else "#FF5252"
        )

        start = mdates.date2num(gap["time"])

        ax.add_patch(
            Rectangle(
                (start, gap["low"]),
                last_date - start + 0.08,
                gap["high"] - gap["low"],
                facecolor=color,
                edgecolor=color,
                alpha=0.25
            )
        )


# ================= CREATE COMBINED CHART =================

def create_chart(name, df12, df1):

    fig, axes = plt.subplots(
        1, 2,
        figsize=(20, 9),
        gridspec_kw={"width_ratios": [1, 1]}
    )

    ax12 = axes[0]
    ax1 = axes[1]

    # LEFT: 12H

    draw_candles(ax12, df12, "12h")

    supports, resistances = find_zones(df12)

    price = df12["close"].iloc[-1]

    zone_width = price * 0.0015

    for level in supports:

        ax12.axhspan(
            level - zone_width,
            level + zone_width,
            color="green",
            alpha=0.2
        )

    for level in resistances:

        ax12.axhspan(
            level - zone_width,
            level + zone_width,
            color="red",
            alpha=0.2
        )

    ax12.set_title(
        "12H | SUPPORT & RESISTANCE",
        fontsize=13
    )

    # RIGHT: 1H

    draw_candles(ax1, df1, "1h")

    draw_order_blocks(ax1, df1)

    draw_fvg(ax1, df1)

    ax1.set_title(
        "1H | ORDER BLOCK & FVG",
        fontsize=13
    )

    # PRICE

    price = df1["close"].iloc[-1]

    fig.text(
        0.5,
        0.025,
        f"{name}     |     ${price:,.4f}",
        ha="center",
        fontsize=17,
        fontweight="bold"
    )

    plt.subplots_adjust(
        bottom=0.12,
        top=0.91,
        wspace=0.12
    )

    filename = f"/tmp/{name}_COMBINED.png"

    plt.savefig(
        filename,
        dpi=160,
        bbox_inches="tight"
    )

    plt.close(fig)

    return filename, price


# ================= TELEGRAM =================

def send_photo(filename, caption):

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendPhoto"
    )

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
            timeout=45
        )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):

        raise Exception(result)


# ================= ANALYSIS =================

def analyze(name):

    print("Analyzing:", name)

    df12 = get_market_data(name, "12h")

    df1 = get_market_data(name, "1h")

    if len(df12) < 30 or len(df1) < 30:

        raise Exception("Insufficient market data")

    filename, price = create_chart(
        name,
        df12,
        df1
    )

    caption = (
        f"📊 {name}\n"
        f"💰 Current Price: ${price:,.4f}"
    )

    send_photo(
        filename,
        caption
    )

    print("SUCCESS:", name)


# ================= MAIN =================

def main():

    if not BOT_TOKEN or not CHANNEL_ID:

        raise Exception(
            "Telegram credentials missing"
        )

    assets = ["BTC", "ETH", "XAU"]

    for name in assets:

        try:

            analyze(name)

        except Exception as e:

            print(f"ERROR {name}: {e}")

        time.sleep(3)


if __name__ == "__main__":

    main()
