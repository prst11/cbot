import hashlib
import hmac
import json
import os
import time
import uuid
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import payments
from shared import COINS, COIN_DISPLAY, display_coin, get_prices, get_price_history

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_USERNAMES = [u.strip() for u in os.getenv("ADMIN_USERNAMES", "").split(",") if u.strip()]
FREE_ALERT_LIMIT = int(os.getenv("FREE_ALERT_LIMIT", "1"))
FREE_PORTFOLIO_LIMIT = int(os.getenv("FREE_PORTFOLIO_LIMIT", "1"))
FREE_CALC_LIMIT = int(os.getenv("FREE_CALC_LIMIT", "5"))
PREMIUM_PRICE_USD = float(os.getenv("PREMIUM_PRICE_USD", "4"))
PREMIUM_DAYS = int(os.getenv("PREMIUM_DAYS", "30"))
REFERRAL_BONUS = int(os.getenv("REFERRAL_BONUS", "5"))
INIT_DATA_MAX_AGE = 86400  # initData от Telegram считаем валидной 24 часа

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def validate_init_data(init_data: str) -> dict:
    """
    Проверяет подлинность initData, присланной Telegram Mini App, по алгоритму из документации Telegram.
    Без этой проверки любой человек мог бы подставить чужой user_id и управлять чужими данными.
    """
    if not init_data or not BOT_TOKEN:
        raise HTTPException(401, "Нет данных авторизации")

    parsed = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "Некорректные данные авторизации")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(401, "Подпись не совпадает")

    auth_date = int(parsed.get("auth_date", "0"))
    if time.time() - auth_date > INIT_DATA_MAX_AGE:
        raise HTTPException(401, "Данные авторизации устарели, перезайди в приложение")

    user = json.loads(parsed.get("user", "{}"))
    return user


def get_current_user(x_telegram_init_data: str = Header(default="")) -> dict:
    user = validate_init_data(x_telegram_init_data)
    if "id" not in user:
        raise HTTPException(401, "Не удалось определить пользователя")
    db.get_or_create_user(user["id"], user.get("username"))
    return user


def is_unlimited(user: dict) -> bool:
    return (user.get("username") in ADMIN_USERNAMES) or db.is_premium(user["id"])


# ─── Инициализация ───
@app.get("/api/init")
def api_init(x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    uid = user["id"]
    return {
        "user_id": uid,
        "lang": db.get_language(uid),
        "is_premium": db.is_premium(uid),
        "premium_days_left": db.premium_days_left(uid),
        "is_admin": user.get("username") in ADMIN_USERNAMES,
        "coins": list(COINS.keys()),
        "coin_display": {k: display_coin(k) for k in COINS},
    }


# ─── Курсы и графики ───
@app.get("/api/prices")
async def api_prices(x_telegram_init_data: str = Header(default="")):
    get_current_user(x_telegram_init_data)
    data = await get_prices()
    result = {}
    for symbol, coin_id in COINS.items():
        if coin_id in data:
            result[symbol] = {
                "usd": data[coin_id]["usd"],
                "change_24h": data[coin_id]["usd_24h_change"],
                "display": display_coin(symbol),
            }
    return result


@app.get("/api/chart/{symbol}")
async def api_chart(symbol: str, x_telegram_init_data: str = Header(default="")):
    get_current_user(x_telegram_init_data)
    coin_id = COINS.get(symbol.upper())
    if not coin_id:
        raise HTTPException(404, "Неизвестная монета")
    history = await get_price_history(coin_id, days=7)
    return {"symbol": symbol.upper(), "points": history}


# ─── Портфель ───
@app.get("/api/portfolio")
async def api_get_portfolio(x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    items = db.get_portfolio(user["id"])
    prices = await get_prices()
    result = []
    total = 0.0
    for item in items:
        coin_id = COINS.get(item["coin"])
        price_data = prices.get(coin_id, {})
        price = price_data.get("usd", 0)
        change = price_data.get("usd_24h_change", 0)
        value = price * item["amount"]
        total += value
        result.append({
            "id": item["id"], "coin": item["coin"], "display": display_coin(item["coin"]),
            "amount": item["amount"], "value": value, "change_24h": change,
        })
    return {"items": result, "total_value": total, "limit": FREE_PORTFOLIO_LIMIT, "unlimited": is_unlimited(user)}


class PortfolioIn(BaseModel):
    coin: str
    amount: float


@app.post("/api/portfolio")
async def api_add_portfolio(body: PortfolioIn, x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    if body.coin not in COINS:
        raise HTTPException(400, "Неизвестная монета")
    if body.amount <= 0:
        raise HTTPException(400, "Количество должно быть больше нуля")
    if not is_unlimited(user) and db.count_portfolio(user["id"]) >= FREE_PORTFOLIO_LIMIT:
        raise HTTPException(402, f"Бесплатно доступно {FREE_PORTFOLIO_LIMIT} монета(ы). Оформи Premium.")
    db.add_portfolio_item(user["id"], body.coin, body.amount)
    return {"ok": True}


@app.delete("/api/portfolio/{item_id}")
async def api_remove_portfolio(item_id: int, x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    db.remove_portfolio_item(user["id"], item_id)
    return {"ok": True}


# ─── Алерты ───
@app.get("/api/alerts")
async def api_get_alerts(x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    alerts = db.get_alerts(user["id"])
    return {
        "items": [
            {
                "id": a["id"], "coin": a["coin"], "display": display_coin(a["coin"]),
                "price": a["price"], "direction": a["direction"],
                "kind": a["kind"], "percent": a["percent"], "base_price": a["base_price"],
            }
            for a in alerts
        ],
        "limit": FREE_ALERT_LIMIT,
        "unlimited": is_unlimited(user),
    }


class AlertIn(BaseModel):
    coin: str
    direction: str
    kind: str = "price"
    price: float | None = None
    percent: float | None = None


@app.post("/api/alerts")
async def api_add_alert(body: AlertIn, x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    if body.coin not in COINS:
        raise HTTPException(400, "Неизвестная монета")
    if body.direction not in ("above", "below"):
        raise HTTPException(400, "direction должен быть above или below")
    if not is_unlimited(user) and db.count_alerts(user["id"]) >= FREE_ALERT_LIMIT:
        raise HTTPException(402, f"Бесплатно доступен {FREE_ALERT_LIMIT} алерт. Оформи Premium.")

    if body.kind == "percent":
        if not body.percent or body.percent <= 0:
            raise HTTPException(400, "Некорректный процент")
        prices = await get_prices()
        coin_id = COINS[body.coin]
        if coin_id not in prices:
            raise HTTPException(503, "Курсы временно недоступны")
        base_price = prices[coin_id]["usd"]
        target_price = (
            base_price * (1 + body.percent / 100) if body.direction == "above"
            else base_price * (1 - body.percent / 100)
        )
        db.add_alert(user["id"], body.coin, target_price, body.direction, kind="percent", percent=body.percent, base_price=base_price)
    else:
        if body.price is None or body.price <= 0:
            raise HTTPException(400, "Некорректная цена")
        db.add_alert(user["id"], body.coin, body.price, body.direction, kind="price")

    return {"ok": True}


@app.delete("/api/alerts/{alert_id}")
async def api_remove_alert(alert_id: int, x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    db.delete_alert(user["id"], alert_id)
    return {"ok": True}


# ─── Избранное (watchlist) ───
@app.get("/api/watchlist")
async def api_get_watchlist(x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    coins = db.get_watchlist(user["id"])
    prices = await get_prices()
    result = []
    for symbol in coins:
        coin_id = COINS.get(symbol)
        price_data = prices.get(coin_id, {})
        result.append({
            "coin": symbol, "display": display_coin(symbol),
            "usd": price_data.get("usd", 0), "change_24h": price_data.get("usd_24h_change", 0),
        })
    return {"items": result}


class WatchIn(BaseModel):
    coin: str


@app.post("/api/watchlist")
async def api_add_watchlist(body: WatchIn, x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    if body.coin not in COINS:
        raise HTTPException(400, "Неизвестная монета")
    db.add_to_watchlist(user["id"], body.coin)
    return {"ok": True}


@app.delete("/api/watchlist/{coin}")
async def api_remove_watchlist(coin: str, x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    db.remove_from_watchlist(user["id"], coin.upper())
    return {"ok": True}


# ─── Калькулятор ───
class CalcIn(BaseModel):
    coin: str
    amount: float


@app.post("/api/calculate")
async def api_calculate(body: CalcIn, x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    used, bonus = db.get_calc_status(user["id"])
    limit = FREE_CALC_LIMIT + bonus
    if not is_unlimited(user) and used >= limit:
        raise HTTPException(402, f"Бесплатно доступно {limit} расчётов. Оформи Premium.")
    if body.coin not in COINS:
        raise HTTPException(400, "Неизвестная монета")

    prices = await get_prices()
    coin_id = COINS[body.coin]
    if coin_id not in prices:
        raise HTTPException(503, "Курсы временно недоступны")

    usd_value = body.amount * prices[coin_id]["usd"]
    conversions = {"USD": round(usd_value, 2)}
    for symbol, cid in COINS.items():
        if symbol == body.coin or cid not in prices:
            continue
        conversions[symbol] = round(usd_value / prices[cid]["usd"], 8)

    if not is_unlimited(user):
        db.increment_calc_used(user["id"])

    used, bonus = db.get_calc_status(user["id"])
    return {"conversions": conversions, "used": used, "limit": FREE_CALC_LIMIT + bonus, "unlimited": is_unlimited(user)}


# ─── Реферальная программа ───
_bot_username_cache = {"value": ""}


async def get_bot_username() -> str:
    if _bot_username_cache["value"]:
        return _bot_username_cache["value"]
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe") as resp:
            data = await resp.json()
    username = data.get("result", {}).get("username", "")
    _bot_username_cache["value"] = username
    return username


@app.get("/api/referral")
async def api_referral(x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    username = await get_bot_username()
    link = f"https://t.me/{username}?start=ref_{user['id']}" if username else ""
    return {"link": link, "count": db.referral_count(user["id"]), "bonus": REFERRAL_BONUS}


# ─── Premium ───
@app.post("/api/premium/create-invoice")
async def api_create_invoice(x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    order_id = f"{user['id']}-{uuid.uuid4().hex[:8]}"
    try:
        invoice = payments.create_invoice(
            amount_usd=PREMIUM_PRICE_USD,
            order_id=order_id,
            description=f"Premium {PREMIUM_DAYS}d for user {user['id']}",
        )
    except Exception:
        raise HTTPException(502, "Не получилось создать платёж")
    payment_id = str(invoice.get("id") or invoice.get("payment_id") or order_id)
    db.create_payment_record(payment_id, user["id"], PREMIUM_PRICE_USD)
    return {"payment_id": payment_id, "invoice_url": invoice.get("invoice_url"), "amount": PREMIUM_PRICE_USD}


@app.post("/api/premium/check/{payment_id}")
async def api_check_payment(payment_id: str, x_telegram_init_data: str = Header(default="")):
    user = get_current_user(x_telegram_init_data)
    try:
        status_data = payments.get_payment_status(payment_id)
    except Exception:
        raise HTTPException(502, "Не получилось проверить платёж")
    if payments.is_payment_successful(status_data):
        db.update_payment_status(payment_id, "finished")
        new_until = db.activate_premium(user["id"], PREMIUM_DAYS)
        return {"confirmed": True, "premium_until": new_until}
    return {"confirmed": False, "status": status_data.get("payment_status", "waiting")}


# ─── Статика веб-приложения (сам интерфейс) — монтируется последним ───
webapp_dir = os.path.join(os.path.dirname(__file__), "webapp")
if os.path.isdir(webapp_dir):
    app.mount("/", StaticFiles(directory=webapp_dir, html=True), name="webapp")
