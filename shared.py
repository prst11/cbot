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


# ─── Кэш текущих курсов на 30 секунд, чтобы не упираться в лимиты CoinGecko ───
_price_cache = {"data": None, "ts": 0}
PRICE_CACHE_TTL = 30


async def get_prices():
    now = time.time()
    if _price_cache["data"] and now - _price_cache["ts"] < PRICE_CACHE_TTL:
        return _price_cache["data"]
    ids = ",".join(COINS.values())
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
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
