import asyncio
import time
import uuid
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import os
from dotenv import load_dotenv

import db
import payments

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не задан. Создай файл .env (по примеру .env.example) "
        "или добавь переменную BOT_TOKEN в настройках Railway."
    )

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ─── Админы и настройки ───
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
if not ADMIN_PASSWORD:
    raise RuntimeError(
        "ADMIN_PASSWORD не задан. Добавь его в .env или в переменные окружения Railway."
    )
ADMIN_USERNAMES = [u.strip() for u in os.getenv("ADMIN_USERNAMES", "").split(",") if u.strip()]
admin_ids = set()
broadcast_state = {}

# ─── Настройки лимитов и премиума ───
FREE_ALERT_LIMIT = int(os.getenv("FREE_ALERT_LIMIT", "1"))
FREE_PORTFOLIO_LIMIT = int(os.getenv("FREE_PORTFOLIO_LIMIT", "1"))
PREMIUM_PRICE_USD = float(os.getenv("PREMIUM_PRICE_USD", "4"))
PREMIUM_DAYS = int(os.getenv("PREMIUM_DAYS", "30"))

COINS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "TON": "the-open-network",
    "SOL": "solana",
    "BNB": "binancecoin",
    "USDT": "tether",
}

# ─── Простой кэш курсов на 30 секунд, чтобы не упираться в лимиты CoinGecko ───
_price_cache = {"data": None, "ts": 0}
PRICE_CACHE_TTL = 30

TEXTS = {
    "ru": {
        "start": "👋 Привет! Я крипто-бот.\n\nСлежу за курсами, портфелем и уведомляю когда цена достигнет нужной отметки 🚀",
        "prices": "📊 Курсы монет",
        "alerts": "🔔 Уведомления",
        "portfolio": "💼 Портфель",
        "premium": "💎 Premium",
        "info": "ℹ️ Информация",
        "donate": "☘️ Донат",
        "language": "🌍 Язык",
        "loading": "⏳ Загружаю курсы...",
        "prices_title": "📊 *Текущие курсы:*\n\n",
        "updated": "\n_Обновлено только что_",
        "error": "❌ Ошибка при загрузке курсов. Попробуй позже.",
        "alerts_title": "🔔 *Уведомления*\n\nАктивных алертов: ",
        "add_alert": "➕ Добавить алерт",
        "my_alerts": "📋 Мои алерты",
        "choose_coin": "Выбери монету:",
        "enter_price": "✅ Монета: *{coin}*\n\nВведи цену в USD (например: `45000`):",
        "enter_number": "❌ Введи число, например: `45000`",
        "when_notify": "Цена: *${price}*\n\nКогда уведомить?",
        "above": "📈 Выше цены",
        "below": "📉 Ниже цены",
        "alert_created": "✅ Алерт создан!\n\n{arrow} *{coin}* — уведомлю когда цена будет {dir} *${price}*",
        "above_text": "выше",
        "below_text": "ниже",
        "no_alerts": "📋 У тебя нет активных алертов.\n\nДобавь первый!",
        "alerts_list": "📋 *Твои алерты:*\n\n",
        "delete": "❌ Удалить #",
        "alert_deleted": "✅ Алерт удалён!",
        "alert_fired": "🔔 *Алерт сработал!*\n\n{arrow} *{coin}* достиг ${current}\nТвоя цель: ${target}",
        "info_text": "ℹ️ *О боте*\n\nСоздатель: @aquaee\nКанал: @TreckerCryptooInfo\n\nБот показывает курсы криптовалют, портфель и присылает уведомления когда цена достигает нужной отметки.",
        "donate_text": "☘️ *Поддержать проект*\n\nTON кошелёк:\n`UQArVnAPk0F6LqrGv3Zx1RPbUeW0SWeI9Ab1M9i81Fci7bKW`\n\nСпасибо! 🙏",
        "choose_language": "🌍 Выбери язык:",
        "language_set": "✅ Язык изменён на Русский!",
        "back": "◀️ Назад",
        "limit_reached_alert": "🔒 Бесплатно доступен {limit} алерт.\n\nОформи Premium — и алертов будет без ограничений.",
        "limit_reached_portfolio": "🔒 Бесплатно доступна {limit} монета в портфеле.\n\nОформи Premium — и монет будет без ограничений.",
        "add_asset": "➕ Добавить монету",
        "my_portfolio": "📋 Мой портфель",
        "enter_amount": "✅ Монета: *{coin}*\n\nВведи количество (например: `0.5`):",
        "asset_added": "✅ Добавлено в портфель: *{amount} {coin}*",
        "portfolio_empty": "💼 Портфель пуст.\n\nДобавь первую монету!",
        "portfolio_title": "💼 *Твой портфель:*\n\n",
        "portfolio_total": "\n💰 *Общая стоимость: ${total}*",
        "portfolio_item": "{arrow} *{coin}*: {amount} (${value:,.2f}, {change:+.2f}%)\n",
        "remove": "❌ Убрать #",
        "asset_removed": "✅ Убрано из портфеля!",
        "premium_active": "💎 *Premium активен*\n\nОсталось дней: *{days}*\n\nБез ограничений на алерты и портфель.",
        "premium_offer": "💎 *Premium*\n\n${price}/мес — безлимитные алерты и монеты в портфеле.\n\nОплата в крипте напрямую.",
        "get_premium": "💎 Оформить Premium",
        "pay_link": "💳 Перейти к оплате",
        "i_paid": "✅ Я оплатил",
        "payment_created": "Счёт создан на ${amount}.\n\nОплати по ссылке ниже, затем нажми «Я оплатил».",
        "payment_confirmed": "🎉 Оплата подтверждена! Premium активирован на {days} дней.",
        "payment_not_yet": "Оплата ещё не подтверждена. Если только что оплатил — подожди 1-2 минуты и попробуй снова.",
        "payment_error": "Не получилось создать платёж, попробуй позже.",
    },
    "en": {
        "start": "👋 Hello! I'm a crypto bot.\n\nI track prices, your portfolio, and notify you when a price hits your target 🚀",
        "prices": "📊 Prices",
        "alerts": "🔔 Alerts",
        "portfolio": "💼 Portfolio",
        "premium": "💎 Premium",
        "info": "ℹ️ Info",
        "donate": "☘️ Donate",
        "language": "🌍 Language",
        "loading": "⏳ Loading prices...",
        "prices_title": "📊 *Current prices:*\n\n",
        "updated": "\n_Just updated_",
        "error": "❌ Error loading prices. Try again later.",
        "alerts_title": "🔔 *Alerts*\n\nActive alerts: ",
        "add_alert": "➕ Add alert",
        "my_alerts": "📋 My alerts",
        "choose_coin": "Choose a coin:",
        "enter_price": "✅ Coin: *{coin}*\n\nEnter price in USD (e.g. `45000`):",
        "enter_number": "❌ Enter a number, e.g. `45000`",
        "when_notify": "Price: *${price}*\n\nWhen to notify?",
        "above": "📈 Above price",
        "below": "📉 Below price",
        "alert_created": "✅ Alert created!\n\n{arrow} *{coin}* — will notify when price is {dir} *${price}*",
        "above_text": "above",
        "below_text": "below",
        "no_alerts": "📋 You have no active alerts.\n\nAdd your first one!",
        "alerts_list": "📋 *Your alerts:*\n\n",
        "delete": "❌ Delete #",
        "alert_deleted": "✅ Alert deleted!",
        "alert_fired": "🔔 *Alert triggered!*\n\n{arrow} *{coin}* reached ${current}\nYour target: ${target}",
        "info_text": "ℹ️ *About bot*\n\nCreator: @aquaee\nChannel: coming soon\n\nThis bot shows crypto prices, your portfolio, and sends alerts when price hits your target.",
        "donate_text": "☘️ *Support the project*\n\nTON wallet:\n`UQArVnAPk0F6LqrGv3Zx1RPbUeW0SWeI9Ab1M9i81Fci7bKW`\n\nThank you! 🙏",
        "choose_language": "🌍 Choose language:",
        "language_set": "✅ Language changed to English!",
        "back": "◀️ Back",
        "limit_reached_alert": "🔒 Free plan includes {limit} alert.\n\nGet Premium for unlimited alerts.",
        "limit_reached_portfolio": "🔒 Free plan includes {limit} coin in portfolio.\n\nGet Premium for unlimited coins.",
        "add_asset": "➕ Add coin",
        "my_portfolio": "📋 My portfolio",
        "enter_amount": "✅ Coin: *{coin}*\n\nEnter amount (e.g. `0.5`):",
        "asset_added": "✅ Added to portfolio: *{amount} {coin}*",
        "portfolio_empty": "💼 Portfolio is empty.\n\nAdd your first coin!",
        "portfolio_title": "💼 *Your portfolio:*\n\n",
        "portfolio_total": "\n💰 *Total value: ${total}*",
        "portfolio_item": "{arrow} *{coin}*: {amount} (${value:,.2f}, {change:+.2f}%)\n",
        "remove": "❌ Remove #",
        "asset_removed": "✅ Removed from portfolio!",
        "premium_active": "💎 *Premium active*\n\nDays left: *{days}*\n\nUnlimited alerts and portfolio coins.",
        "premium_offer": "💎 *Premium*\n\n${price}/mo — unlimited alerts and portfolio coins.\n\nPay directly in crypto.",
        "get_premium": "💎 Get Premium",
        "pay_link": "💳 Go to payment",
        "i_paid": "✅ I paid",
        "payment_created": "Invoice created for ${amount}.\n\nPay using the link below, then tap «I paid».",
        "payment_confirmed": "🎉 Payment confirmed! Premium activated for {days} days.",
        "payment_not_yet": "Payment not confirmed yet. If you just paid — wait 1-2 minutes and try again.",
        "payment_error": "Couldn't create the payment, try again later.",
    }
}


def t(user_id, key):
    lang = db.get_language(user_id)
    return TEXTS[lang][key]


class AlertState(StatesGroup):
    waiting_coin = State()
    waiting_price = State()
    waiting_direction = State()


class PortfolioState(StatesGroup):
    waiting_coin = State()
    waiting_amount = State()


class AdminState(StatesGroup):
    waiting_password = State()


def main_keyboard(user_id):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(user_id, "prices")), KeyboardButton(text=t(user_id, "alerts"))],
            [KeyboardButton(text=t(user_id, "portfolio")), KeyboardButton(text=t(user_id, "premium"))],
            [KeyboardButton(text=t(user_id, "info")), KeyboardButton(text=t(user_id, "donate"))],
            [KeyboardButton(text=t(user_id, "language"))],
        ],
        resize_keyboard=True
    )


def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка всем", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="❌ Выйти из админки", callback_data="admin_exit")],
    ])


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


def update_user_stats(user_id, username=None):
    db.get_or_create_user(user_id, username)


# ─── /start ───
@dp.message(CommandStart())
async def start(message: Message):
    uid = message.from_user.id
    username = message.from_user.username or ""
    update_user_stats(uid, username)
    if username in ADMIN_USERNAMES:
        admin_ids.add(uid)
    await message.answer(t(uid, "start"), reply_markup=main_keyboard(uid))


# ─── /admin ───
@dp.message(Command("admin"))
async def admin_command(message: Message, state: FSMContext):
    uid = message.from_user.id
    username = message.from_user.username or ""
    if uid in admin_ids or username in ADMIN_USERNAMES:
        admin_ids.add(uid)
        await message.answer("👑 *Админ панель*", parse_mode="Markdown", reply_markup=admin_keyboard())
        return
    await message.answer("🔐 Введи пароль:")
    await state.set_state(AdminState.waiting_password)


# ─── Пароль ───
@dp.message(AdminState.waiting_password)
async def check_password(message: Message, state: FSMContext):
    uid = message.from_user.id
    if message.text == ADMIN_PASSWORD:
        admin_ids.add(uid)
        await state.clear()
        await message.answer("✅ Доступ разрешён!\n\n👑 *Админ панель*", parse_mode="Markdown", reply_markup=admin_keyboard())
    else:
        await state.clear()
        await message.answer("❌ Неверный пароль!")


# ─── Админ: пользователи ───
@dp.callback_query(F.data == "admin_users")
async def admin_users(call: CallbackQuery):
    if call.from_user.id not in admin_ids:
        await call.answer("❌ Нет доступа!", show_alert=True)
        return
    s = db.stats_summary()
    text = (
        "👥 *Пользователи*\n\n"
        f"📊 Всего: *{s['total']}*\n"
        f"🟢 Активны сегодня: *{s['active_today']}*\n"
        f"🔔 С алертами: *{s['with_alerts']}*\n"
        f"💎 Premium: *{s['premium']}*\n"
    )
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]))


# ─── Админ: статистика ───
@dp.callback_query(F.data == "admin_stats")
async def admin_stats_cb(call: CallbackQuery):
    if call.from_user.id not in admin_ids:
        await call.answer("❌ Нет доступа!", show_alert=True)
        return
    s = db.stats_summary()
    text = (
        "📊 *Статистика*\n\n"
        f"👥 Пользователей: *{s['total']}*\n"
        f"🔔 Активных алертов: *{s['total_alerts']}*\n"
        f"💎 Premium: *{s['premium']}*\n"
        f"🇷🇺 Русский: *{s['ru_users']}*\n"
        f"🇬🇧 English: *{s['en_users']}*\n"
        f"👑 Админов: *{len(admin_ids)}*\n"
    )
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]))


# ─── Админ: рассылка ───
@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(call: CallbackQuery):
    if call.from_user.id not in admin_ids:
        await call.answer("❌ Нет доступа!", show_alert=True)
        return
    broadcast_state[call.from_user.id] = True
    await call.message.edit_text(
        "📢 *Рассылка*\n\nНапиши сообщение — его получат все пользователи бота:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")]
        ])
    )


# ─── Назад ───
@dp.callback_query(F.data == "admin_back")
async def admin_back(call: CallbackQuery):
    if call.from_user.id not in admin_ids:
        await call.answer("❌ Нет доступа!", show_alert=True)
        return
    await call.message.edit_text("👑 *Админ панель*", parse_mode="Markdown", reply_markup=admin_keyboard())


# ─── Выход ───
@dp.callback_query(F.data == "admin_exit")
async def admin_exit(call: CallbackQuery):
    uid = call.from_user.id
    username = call.from_user.username or ""
    if username not in ADMIN_USERNAMES:
        admin_ids.discard(uid)
    await call.message.edit_text("👋 Вышел из админ панели.")


# ─── Курсы ───
@dp.message(F.text.in_(["📊 Курсы монет", "📊 Prices"]))
async def show_prices(message: Message):
    uid = message.from_user.id
    update_user_stats(uid)
    await message.answer(t(uid, "loading"))
    try:
        data = await get_prices()
        text = t(uid, "prices_title")
        for symbol, coin_id in COINS.items():
            price = data[coin_id]["usd"]
            change = data[coin_id]["usd_24h_change"]
            arrow = "🟢" if change >= 0 else "🔴"
            text += f"{arrow} *{symbol}*: ${price:,.2f}  ({change:+.2f}%)\n"
        text += t(uid, "updated")
        await message.answer(text, parse_mode="Markdown")
    except Exception:
        await message.answer(t(uid, "error"))


# ─── Уведомления ───
@dp.message(F.text.in_(["🔔 Уведомления", "🔔 Alerts"]))
async def alerts_menu(message: Message):
    uid = message.from_user.id
    update_user_stats(uid)
    count = db.count_alerts(uid)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid, "add_alert"), callback_data="add_alert")],
        [InlineKeyboardButton(text=t(uid, "my_alerts"), callback_data="my_alerts")],
    ])
    await message.answer(t(uid, "alerts_title") + str(count), parse_mode="Markdown", reply_markup=keyboard)


@dp.callback_query(F.data == "add_alert")
async def add_alert_step1(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not db.is_premium(uid) and db.count_alerts(uid) >= FREE_ALERT_LIMIT:
        await call.message.edit_text(
            t(uid, "limit_reached_alert").format(limit=FREE_ALERT_LIMIT),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(uid, "get_premium"), callback_data="premium_buy")],
            ])
        )
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s, callback_data=f"coin_{s}") for s in list(COINS.keys())[:3]],
        [InlineKeyboardButton(text=s, callback_data=f"coin_{s}") for s in list(COINS.keys())[3:]],
    ])
    await call.message.edit_text(t(uid, "choose_coin"), reply_markup=keyboard)
    await state.set_state(AlertState.waiting_coin)


@dp.callback_query(F.data.startswith("coin_"))
async def add_alert_step2(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    coin = call.data.replace("coin_", "")
    await state.update_data(coin=coin)
    await call.message.edit_text(t(uid, "enter_price").format(coin=coin), parse_mode="Markdown")
    await state.set_state(AlertState.waiting_price)


@dp.message(AlertState.waiting_price)
async def add_alert_step3(message: Message, state: FSMContext):
    uid = message.from_user.id
    try:
        price = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer(t(uid, "enter_number"), parse_mode="Markdown")
        return
    await state.update_data(price=price)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid, "above"), callback_data="dir_above")],
        [InlineKeyboardButton(text=t(uid, "below"), callback_data="dir_below")],
    ])
    await message.answer(t(uid, "when_notify").format(price=f"{price:,.2f}"), parse_mode="Markdown", reply_markup=keyboard)
    await state.set_state(AlertState.waiting_direction)


@dp.callback_query(F.data.startswith("dir_"))
async def add_alert_step4(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    direction = "above" if call.data == "dir_above" else "below"
    data = await state.get_data()
    db.add_alert(uid, data["coin"], data["price"], direction)
    arrow = "📈" if direction == "above" else "📉"
    dir_text = t(uid, "above_text") if direction == "above" else t(uid, "below_text")
    await call.message.edit_text(
        t(uid, "alert_created").format(arrow=arrow, coin=data["coin"], dir=dir_text, price=f"{data['price']:,.2f}"),
        parse_mode="Markdown"
    )
    await state.clear()


@dp.callback_query(F.data == "my_alerts")
async def show_alerts(call: CallbackQuery):
    uid = call.from_user.id
    user_alerts = db.get_alerts(uid)
    if not user_alerts:
        await call.message.edit_text(t(uid, "no_alerts"))
        return
    text = t(uid, "alerts_list")
    buttons = []
    for a in user_alerts:
        arrow = "📈" if a["direction"] == "above" else "📉"
        dir_text = t(uid, "above_text") if a["direction"] == "above" else t(uid, "below_text")
        text += f"{arrow} *{a['coin']}* {dir_text} ${a['price']:,.2f}\n"
        buttons.append([InlineKeyboardButton(text=t(uid, "delete") + str(a["id"]), callback_data=f"del_{a['id']}")])
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("del_"))
async def delete_alert_cb(call: CallbackQuery):
    uid = call.from_user.id
    alert_id = int(call.data.replace("del_", ""))
    db.delete_alert(uid, alert_id)
    await call.answer(t(uid, "alert_deleted"))
    await show_alerts(call)


# ─── Портфель ───
@dp.message(F.text.in_(["💼 Портфель", "💼 Portfolio"]))
async def portfolio_menu(message: Message):
    uid = message.from_user.id
    update_user_stats(uid)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid, "add_asset"), callback_data="add_asset")],
        [InlineKeyboardButton(text=t(uid, "my_portfolio"), callback_data="my_portfolio")],
    ])
    await message.answer(t(uid, "portfolio"), reply_markup=keyboard)


@dp.callback_query(F.data == "add_asset")
async def add_asset_step1(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not db.is_premium(uid) and db.count_portfolio(uid) >= FREE_PORTFOLIO_LIMIT:
        await call.message.edit_text(
            t(uid, "limit_reached_portfolio").format(limit=FREE_PORTFOLIO_LIMIT),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(uid, "get_premium"), callback_data="premium_buy")],
            ])
        )
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s, callback_data=f"pcoin_{s}") for s in list(COINS.keys())[:3]],
        [InlineKeyboardButton(text=s, callback_data=f"pcoin_{s}") for s in list(COINS.keys())[3:]],
    ])
    await call.message.edit_text(t(uid, "choose_coin"), reply_markup=keyboard)
    await state.set_state(PortfolioState.waiting_coin)


@dp.callback_query(F.data.startswith("pcoin_"))
async def add_asset_step2(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    coin = call.data.replace("pcoin_", "")
    await state.update_data(coin=coin)
    await call.message.edit_text(t(uid, "enter_amount").format(coin=coin), parse_mode="Markdown")
    await state.set_state(PortfolioState.waiting_amount)


@dp.message(PortfolioState.waiting_amount)
async def add_asset_step3(message: Message, state: FSMContext):
    uid = message.from_user.id
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer(t(uid, "enter_number"), parse_mode="Markdown")
        return
    data = await state.get_data()
    db.add_portfolio_item(uid, data["coin"], amount)
    await message.answer(t(uid, "asset_added").format(amount=amount, coin=data["coin"]), parse_mode="Markdown")
    await state.clear()


@dp.callback_query(F.data == "my_portfolio")
async def show_portfolio(call: CallbackQuery):
    uid = call.from_user.id
    items = db.get_portfolio(uid)
    if not items:
        await call.message.edit_text(t(uid, "portfolio_empty"))
        return
    try:
        prices = await get_prices()
    except Exception:
        await call.message.edit_text(t(uid, "error"))
        return

    text = t(uid, "portfolio_title")
    buttons = []
    total = 0.0
    for item in items:
        coin_id = COINS.get(item["coin"])
        if not coin_id or coin_id not in prices:
            continue
        price = prices[coin_id]["usd"]
        change = prices[coin_id]["usd_24h_change"]
        value = price * item["amount"]
        total += value
        arrow = "🟢" if change >= 0 else "🔴"
        text += t(uid, "portfolio_item").format(arrow=arrow, coin=item["coin"], amount=item["amount"], value=value, change=change)
        buttons.append([InlineKeyboardButton(text=t(uid, "remove") + str(item["id"]), callback_data=f"prem_{item['id']}")])
    text += t(uid, "portfolio_total").format(total=f"{total:,.2f}")
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("prem_"))
async def remove_asset_cb(call: CallbackQuery):
    uid = call.from_user.id
    item_id = int(call.data.replace("prem_", ""))
    db.remove_portfolio_item(uid, item_id)
    await call.answer(t(uid, "asset_removed"))
    await show_portfolio(call)


# ─── Premium ───
@dp.message(F.text.in_(["💎 Premium"]))
async def premium_menu(message: Message):
    uid = message.from_user.id
    update_user_stats(uid)
    if db.is_premium(uid):
        days = db.premium_days_left(uid)
        await message.answer(t(uid, "premium_active").format(days=days), parse_mode="Markdown")
        return
    await message.answer(
        t(uid, "premium_offer").format(price=PREMIUM_PRICE_USD),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(uid, "get_premium"), callback_data="premium_buy")],
        ])
    )


@dp.callback_query(F.data == "premium_buy")
async def premium_buy(call: CallbackQuery):
    uid = call.from_user.id
    order_id = f"{uid}-{uuid.uuid4().hex[:8]}"
    try:
        invoice = payments.create_invoice(
            amount_usd=PREMIUM_PRICE_USD,
            order_id=order_id,
            description=f"Premium {PREMIUM_DAYS}d for user {uid}",
        )
    except Exception:
        await call.answer(t(uid, "payment_error"), show_alert=True)
        return

    payment_id = str(invoice.get("id") or invoice.get("payment_id") or order_id)
    invoice_url = invoice.get("invoice_url")
    db.create_payment_record(payment_id, uid, PREMIUM_PRICE_USD)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid, "pay_link"), url=invoice_url)],
        [InlineKeyboardButton(text=t(uid, "i_paid"), callback_data=f"checkpay_{payment_id}")],
    ])
    await call.message.edit_text(
        t(uid, "payment_created").format(amount=PREMIUM_PRICE_USD),
        reply_markup=kb,
    )


@dp.callback_query(F.data.startswith("checkpay_"))
async def check_payment_cb(call: CallbackQuery):
    uid = call.from_user.id
    payment_id = call.data.replace("checkpay_", "")
    try:
        status_data = payments.get_payment_status(payment_id)
    except Exception:
        await call.answer(t(uid, "payment_not_yet"), show_alert=True)
        return

    if payments.is_payment_successful(status_data):
        db.update_payment_status(payment_id, "finished")
        db.activate_premium(uid, PREMIUM_DAYS)
        await call.message.edit_text(t(uid, "payment_confirmed").format(days=PREMIUM_DAYS), parse_mode="Markdown")
    else:
        await call.answer(t(uid, "payment_not_yet"), show_alert=True)


# ─── Инфо ───
@dp.message(F.text.in_(["ℹ️ Информация", "ℹ️ Info"]))
async def info(message: Message):
    update_user_stats(message.from_user.id)
    await message.answer(t(message.from_user.id, "info_text"), parse_mode="Markdown")


# ─── Донат ───
@dp.message(F.text.in_(["☘️ Донат", "☘️ Donate"]))
async def donate(message: Message):
    update_user_stats(message.from_user.id)
    await message.answer(t(message.from_user.id, "donate_text"), parse_mode="Markdown")


# ─── Язык ───
@dp.message(F.text.in_(["🌍 Язык", "🌍 Language"]))
async def language_menu(message: Message):
    update_user_stats(message.from_user.id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
    ])
    await message.answer(t(message.from_user.id, "choose_language"), reply_markup=keyboard)


@dp.callback_query(F.data.startswith("lang_"))
async def set_language(call: CallbackQuery):
    uid = call.from_user.id
    lang = call.data.replace("lang_", "")
    db.set_language(uid, lang)
    await call.message.edit_text(t(uid, "language_set"))
    await call.message.answer(t(uid, "start"), reply_markup=main_keyboard(uid))


# ─── Обработка текста (рассылка) ───
@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    uid = message.from_user.id
    update_user_stats(uid)
    if uid in broadcast_state and broadcast_state.get(uid):
        broadcast_state.pop(uid)
        sent = 0
        failed = 0
        for user_id in db.all_user_ids():
            try:
                await bot.send_message(user_id, f"📢 *Сообщение от администратора:*\n\n{message.text}", parse_mode="Markdown")
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)  # не упираемся в лимиты Telegram на рассылку
        await message.answer(f"✅ Готово!\n\nОтправлено: {sent}\nОшибок: {failed}", reply_markup=admin_keyboard())


# ─── Фоновая проверка алертов ───
async def check_alerts():
    while True:
        await asyncio.sleep(60)
        alerts = db.get_all_alerts()
        if not alerts:
            continue
        try:
            data = await get_prices()
            for alert in alerts:
                coin_id = COINS.get(alert["coin"])
                if not coin_id or coin_id not in data:
                    continue
                current_price = data[coin_id]["usd"]
                triggered = (
                    alert["direction"] == "above" and current_price >= alert["price"] or
                    alert["direction"] == "below" and current_price <= alert["price"]
                )
                if triggered:
                    arrow = "📈" if alert["direction"] == "above" else "📉"
                    uid = alert["user_id"]
                    try:
                        await bot.send_message(
                            uid,
                            t(uid, "alert_fired").format(
                                arrow=arrow,
                                coin=alert["coin"],
                                current=f"{current_price:,.2f}",
                                target=f"{alert['price']:,.2f}"
                            ),
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass
                    db.delete_alert_by_id(alert["id"])
        except Exception:
            pass


async def main():
    db.init_db()
    asyncio.create_task(check_alerts())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
