import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import os
from datetime import datetime
from dotenv import load_dotenv

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
# Список юзернеймов админов через запятую в .env, например: ADMIN_USERNAMES=aquaee,underworldcrush
ADMIN_USERNAMES = [u.strip() for u in os.getenv("ADMIN_USERNAMES", "").split(",") if u.strip()]
admin_ids = set()
user_languages = {}
alerts = {}
broadcast_state = {}

# Статистика
stats = {
    "total_users": set(),
    "active_today": set(),
    "join_dates": {},
    "last_seen": {},
}

COINS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "TON": "the-open-network",
    "SOL": "solana",
    "BNB": "binancecoin",
    "USDT": "tether",
}

TEXTS = {
    "ru": {
        "start": "👋 Привет! Я крипто-бот.\n\nСлежу за курсами и уведомляю когда цена достигнет нужной отметки 🚀",
        "prices": "📊 Курсы монет",
        "alerts": "🔔 Уведомления",
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
        "info_text": "ℹ️ *О боте*\n\nСоздатель: @aquaee\nКанал: @TreckerCryptooInfo\n\nБот показывает курсы криптовалют и присылает уведомления когда цена достигает нужной отметки.",
        "donate_text": "☘️ *Поддержать проект*\n\nTON кошелёк:\n`UQArVnAPk0F6LqrGv3Zx1RPbUeW0SWeI9Ab1M9i81Fci7bKW`\n\nСпасибо! 🙏",
        "choose_language": "🌍 Выбери язык:",
        "language_set": "✅ Язык изменён на Русский!",
        "back": "◀️ Назад",
    },
    "en": {
        "start": "👋 Hello! I'm a crypto bot.\n\nI track prices and notify you when a price hits your target 🚀",
        "prices": "📊 Prices",
        "alerts": "🔔 Alerts",
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
        "info_text": "ℹ️ *About bot*\n\nCreator: @aquaee\nChannel: coming soon\n\nThis bot shows crypto prices and sends alerts when price hits your target.",
        "donate_text": "☘️ *Support the project*\n\nTON wallet:\n`UQArVnAPk0F6LqrGv3Zx1RPbUeW0SWeI9Ab1M9i81Fci7bKW`\n\nThank you! 🙏",
        "choose_language": "🌍 Choose language:",
        "language_set": "✅ Language changed to English!",
        "back": "◀️ Back",
    }
}

def t(user_id, key):
    lang = user_languages.get(user_id, "ru")
    return TEXTS[lang][key]

class AlertState(StatesGroup):
    waiting_coin = State()
    waiting_price = State()
    waiting_direction = State()

class AdminState(StatesGroup):
    waiting_password = State()

def main_keyboard(user_id):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(user_id, "prices")), KeyboardButton(text=t(user_id, "alerts"))],
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
    ids = ",".join(COINS.values())
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

def update_user_stats(user_id):
    stats["total_users"].add(user_id)
    stats["active_today"].add(user_id)
    stats["last_seen"][user_id] = datetime.now()
    if user_id not in stats["join_dates"]:
        stats["join_dates"][user_id] = datetime.now()

# ─── /start ───
@dp.message(CommandStart())
async def start(message: Message):
    uid = message.from_user.id
    username = message.from_user.username or ""
    update_user_stats(uid)
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
    total = len(stats["total_users"])
    active = len(stats["active_today"])
    with_alerts = sum(1 for uid in alerts if alerts[uid])
    text = (
        "👥 *Пользователи*\n\n"
        f"📊 Всего: *{total}*\n"
        f"🟢 Активны сегодня: *{active}*\n"
        f"🔔 С алертами: *{with_alerts}*\n"
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
    total_alerts = sum(len(v) for v in alerts.values())
    ru_users = sum(1 for lang in user_languages.values() if lang == "ru")
    en_users = sum(1 for lang in user_languages.values() if lang == "en")
    text = (
        "📊 *Статистика*\n\n"
        f"👥 Пользователей: *{len(stats['total_users'])}*\n"
        f"🔔 Активных алертов: *{total_alerts}*\n"
        f"🇷🇺 Русский: *{ru_users}*\n"
        f"🇬🇧 English: *{en_users}*\n"
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
    user_alerts = alerts.get(uid, [])
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid, "add_alert"), callback_data="add_alert")],
        [InlineKeyboardButton(text=t(uid, "my_alerts"), callback_data="my_alerts")],
    ])
    await message.answer(t(uid, "alerts_title") + str(len(user_alerts)), parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data == "add_alert")
async def add_alert_step1(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
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
    if uid not in alerts:
        alerts[uid] = []
    alerts[uid].append({"coin": data["coin"], "price": data["price"], "direction": direction})
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
    user_alerts = alerts.get(uid, [])
    if not user_alerts:
        await call.message.edit_text(t(uid, "no_alerts"))
        return
    text = t(uid, "alerts_list")
    buttons = []
    for i, a in enumerate(user_alerts):
        arrow = "📈" if a["direction"] == "above" else "📉"
        dir_text = t(uid, "above_text") if a["direction"] == "above" else t(uid, "below_text")
        text += f"{i+1}. {arrow} *{a['coin']}* {dir_text} ${a['price']:,.2f}\n"
        buttons.append([InlineKeyboardButton(text=t(uid, "delete") + str(i+1), callback_data=f"del_{i}")])
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("del_"))
async def delete_alert_cb(call: CallbackQuery):
    uid = call.from_user.id
    index = int(call.data.replace("del_", ""))
    if uid in alerts and index < len(alerts[uid]):
        alerts[uid].pop(index)
    await call.answer(t(uid, "alert_deleted"))
    await show_alerts(call)

# ─── Инфо ───
@dp.message(F.text.in_(["ℹ️ Информация", "ℹ️ Info"]))
async def info(message: Message):
    await message.answer(t(message.from_user.id, "info_text"), parse_mode="Markdown")

# ─── Донат ───
@dp.message(F.text.in_(["☘️ Донат", "☘️ Donate"]))
async def donate(message: Message):
    await message.answer(t(message.from_user.id, "donate_text"), parse_mode="Markdown")

# ─── Язык ───
@dp.message(F.text.in_(["🌍 Язык", "🌍 Language"]))
async def language_menu(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
    ])
    await message.answer(t(message.from_user.id, "choose_language"), reply_markup=keyboard)

@dp.callback_query(F.data.startswith("lang_"))
async def set_language(call: CallbackQuery):
    uid = call.from_user.id
    lang = call.data.replace("lang_", "")
    user_languages[uid] = lang
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
        for user_id in list(stats["total_users"]):
            try:
                await bot.send_message(user_id, f"📢 *Сообщение от администратора:*\n\n{message.text}", parse_mode="Markdown")
                sent += 1
            except Exception:
                failed += 1
        await message.answer(f"✅ Готово!\n\nОтправлено: {sent}\nОшибок: {failed}", reply_markup=admin_keyboard())

# ─── Фоновая проверка ───
async def check_alerts():
    while True:
        await asyncio.sleep(60)
        if not alerts:
            continue
        try:
            data = await get_prices()
            for uid, user_alerts in list(alerts.items()):
                to_remove = []
                for i, alert in enumerate(user_alerts):
                    coin_id = COINS.get(alert["coin"])
                    if not coin_id:
                        continue
                    current_price = data[coin_id]["usd"]
                    triggered = (
                        alert["direction"] == "above" and current_price >= alert["price"] or
                        alert["direction"] == "below" and current_price <= alert["price"]
                    )
                    if triggered:
                        arrow = "📈" if alert["direction"] == "above" else "📉"
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
                        to_remove.append(i)
                for i in reversed(to_remove):
                    user_alerts.pop(i)
        except Exception:
            pass

async def main():
    asyncio.create_task(check_alerts())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
