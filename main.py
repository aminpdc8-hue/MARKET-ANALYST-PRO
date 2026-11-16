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
