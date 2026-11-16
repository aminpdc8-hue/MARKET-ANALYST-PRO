import os
import json
import asyncio
import requests
from playwright.async_api import async_playwright

# =============== CONFIG ===============

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

CHARTS = {
    "BTC": "BINANCE:BTCUSDT",
    "ETH": "BINANCE:ETHUSDT",
    "XAU": "OANDA:XAUUSD"
}

TRADINGVIEW_URL = (
    "https://s3.tradingview.com/"
    "external-embedding/embed-widget-advanced-chart.js"
)

# =============== TELEGRAM ===============

def send_photo(path, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    with open(path, "rb") as photo:
        response = requests.post(
            url,
            data={
                "chat_id": CHANNEL_ID,
                "caption": caption
            },
            files={"photo": photo},
            timeout=60
        )

    response.raise_for_status()


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHANNEL_ID,
            "text": text
        },
        timeout=30
    )

    response.raise_for_status()


# =============== TRADINGVIEW CHART ===============

async def create_chart(browser, name, symbol):

    page = await browser.new_page(
        viewport={"width": 1400, "height": 850},
        device_scale_factor=1
    )

    config = {
        "autosize": True,
        "symbol": symbol,
        "interval": "720",
        "timezone": "Asia/Tehran",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "hide_top_toolbar": True,
        "hide_side_toolbar": True,
        "hide_legend": True,
        "hide_volume": False,
        "allow_symbol_change": False,
        "withdateranges": False,
        "save_image": False,
        "calendar": False,
        "studies": [
            "MASimple@tv-basicstudies",
            "RSI@tv-basicstudies",
            "MACD@tv-basicstudies"
        ],
        "support_host": "https://www.tradingview.com"
    }

    html = f"""
    <html>
    <head>
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
                background: #131722;
                overflow: hidden;
            }}
            .tradingview-widget-container {{
                width: 100%;
                height: 100%;
            }}
            .tradingview-widget-container__widget {{
                width: 100%;
                height: 100%;
            }}
        </style>
    </head>
    <body>
        <div class="tradingview-widget-container">
            <div class="tradingview-widget-container__widget"></div>
            <script src="{TRADINGVIEW_URL}" async>
                {json.dumps(config)}
            </script>
        </div>
    </body>
    </html>
    """

    await page.set_content(html, wait_until="domcontentloaded")
    await page.wait_for_timeout(35000)

    path = f"/tmp/{name}.png"
    await page.screenshot(path=path)

    await page.close()
    return path


# =============== MAIN ===============

async def main():

    if not BOT_TOKEN or not CHANNEL_ID:
        raise RuntimeError("Telegram secrets are missing!")

    async with async_playwright() as p:

        browser = await p.chromium.launch()

        send_message(
            "📊 MARKET ANALYST PRO\n"
            "شروع گزارش بازار\n"
            "⏱ تایم‌فریم: 12H\n"
            "📈 منبع نمودار: TradingView"
        )

        for name, symbol in CHARTS.items():

            try:
                print(f"Creating chart: {name}")

                image_path = await create_chart(
                    browser,
                    name,
                    symbol
                )

                send_photo(
                    image_path,
                    f"{name} | نمودار 12 ساعته"
                )

                print(f"Sent: {name}")

            except Exception as error:
                print(f"ERROR {name}: {error}")

                send_message(
                    f"⚠️ خطا در دریافت نمودار {name}\n{error}"
                )

        await browser.close()

    send_message("✅ گزارش سه بازار به پایان رسید.")


if __name__ == "__main__":
    asyncio.run(main())
