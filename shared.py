import os
import time
import aiohttp

COINS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "TON": "the-open-network",
    "SOL": "solana",
    "BNB": "binancecoin",
    "USDT": "tether",
}

# Кастомные отображаемые названия монет (внутренние ключи COINS не трогаем — на них завязана логика)
COIN_DISPLAY = {
    "TON": "GRAM (TON)",
}


def display_coin(symbol: str) -> str:
    return COIN_DISPLAY.get(symbol, symbol)


DISPLAY_CURRENCIES = ["usd", "uah", "eur"]

# ─── Кэш текущих курсов на 30 секунд, чтобы не упираться в лимиты CoinGecko ───
_price_cache = {"data": None, "ts": 0}
PRICE_CACHE_TTL = 30


async def get_prices():
    now = time.time()
    if _price_cache["data"] and now - _price_cache["ts"] < PRICE_CACHE_TTL:
        return _price_cache["data"]
    ids = ",".join(COINS.values())
    vs = ",".join(DISPLAY_CURRENCIES)
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies={vs}&include_24hr_change=true"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
    _price_cache["data"] = data
    _price_cache["ts"] = now
    return data


# ─── Кэш истории цен (для графиков) на 5 минут — история меняется не так часто ───
_history_cache: dict[str, dict] = {}
HISTORY_CACHE_TTL = 300


async def get_price_history(coin_id: str, days: int = 7):
    now = time.time()
    cached = _history_cache.get(coin_id)
    if cached and now - cached["ts"] < HISTORY_CACHE_TTL:
        return cached["data"]
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
    prices = data.get("prices", [])  # список [timestamp_ms, price]
    _history_cache[coin_id] = {"data": prices, "ts": now}
    return prices


# ─── Кэш крипто-новостей на 10 минут ───
_news_cache = {"data": None, "ts": 0}
NEWS_CACHE_TTL = 600


async def get_news(limit: int = 6):
    now = time.time()
    if _news_cache["data"] and now - _news_cache["ts"] < NEWS_CACHE_TTL:
        return _news_cache["data"][:limit]
    url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                raw = await resp.json()
        items = [
            {
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "source": a.get("source_info", {}).get("name") or a.get("source", ""),
                "published_at": a.get("published_on", 0),
                "image": a.get("imageurl", ""),
            }
            for a in raw.get("Data", [])[:20]
        ]
        _news_cache["data"] = items
        _news_cache["ts"] = now
        return items[:limit]
    except Exception:
        # если новостной API недоступен — отдаём то, что было в кэше раньше (даже устаревшее), либо пусто
        return (_news_cache["data"] or [])[:limit]
