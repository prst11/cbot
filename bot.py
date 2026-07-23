import asyncio
import logging
import time
import uuid
import aiohttp
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import os
from dotenv import load_dotenv

import db
import payments
from shared import COINS, COIN_DISPLAY, display_coin, get_prices, get_suggested_alert_percent

load_dotenv()
logging.basicConfig(level=logging.INFO)

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
PREMIUM_YEARLY_PRICE_USD = float(os.getenv("PREMIUM_YEARLY_PRICE_USD", "30"))
PREMIUM_YEARLY_DAYS = int(os.getenv("PREMIUM_YEARLY_DAYS", "365"))
FREE_CALC_LIMIT = int(os.getenv("FREE_CALC_LIMIT", "5"))
MINI_APP_URL = os.getenv("MINI_APP_URL", "").strip()
if MINI_APP_URL and not MINI_APP_URL.startswith("https://"):
    logging.warning(
        f"MINI_APP_URL='{MINI_APP_URL}' не начинается с https:// — Telegram требует именно HTTPS. "
        "Кнопка Mini App отключена, пока переменная не будет исправлена в Variables на Railway."
    )
    MINI_APP_URL = ""
REFERRAL_BONUS = int(os.getenv("REFERRAL_BONUS", "5"))
DAILY_SUMMARY_HOUR_UTC = int(os.getenv("DAILY_SUMMARY_HOUR_UTC", "9"))
CURRENCY_SYMBOLS = {"usd": "$", "uah": "₴", "eur": "€"}
BOT_USERNAME = ""  # заполнится при старте через bot.get_me()

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
        "bucket_holding": "📦 Холд",
        "bucket_trading": "⚡ Трейдинг",
        "choose_bucket": "В какую корзину добавить монету?",
        "enter_amount": "✅ Монета: *{coin}*\n\nВведи количество (например: `0.5`):",
        "asset_added": "✅ Добавлено в портфель: *{amount} {coin}*",
        "portfolio_empty": "💼 Портфель пуст.\n\nДобавь первую монету!",
        "portfolio_title": "💼 *Твой портфель:*\n\n",
        "portfolio_total": "\n💰 *Общая стоимость: {symbol}{total}*",
        "portfolio_item": "{arrow} *{coin}*: {amount} ({symbol}{value:,.2f}, {change:+.2f}%)\n",
        "remove": "❌ Убрать #",
        "asset_removed": "✅ Убрано из портфеля!",
        "premium_active": "💎 *Premium активен*\n\nОсталось дней: *{days}*\n\nБез ограничений на алерты и портфель.",
        "premium_offer": "💎 *Premium*\n\n${price}/мес — безлимитные алерты и монеты в портфеле.\n\nОплата в крипте напрямую.",
        "get_premium": "💎 Оформить Premium",
        "get_premium_month": "💳 Месяц — ${price}",
        "get_premium_year": "🎁 Год — ${price} (выгода {savings}%)",
        "pay_link": "💳 Перейти к оплате",
        "i_paid": "✅ Я оплатил",
        "payment_created": "Счёт создан на ${amount}.\n\nОплати по ссылке ниже, затем нажми «Я оплатил».",
        "payment_confirmed": "🎉 Оплата подтверждена! Premium активирован на {days} дней.",
        "payment_not_yet": "Оплата ещё не подтверждена. Если только что оплатил — подожди 1-2 минуты и попробуй снова.",
        "payment_error": "Не получилось создать платёж, попробуй позже.",
        "calculator": "🧮 Калькулятор",
        "calc_choose_coin": "Из какой валюты считаем?",
        "calc_enter_amount": "✅ Валюта: *{coin}*\n\nВведи количество (например: `1.5`):",
        "calc_result_header": "🧮 *{amount} {coin} =*\n\n",
        "calc_limit_reached": "🔒 Бесплатно доступно {limit} расчётов.\n\nОформи Premium — и расчётов будет без ограничений.",
        "choose_mode": "👋 Привет! Я крипто-бот.\n\nКак удобнее пользоваться?",
        "mode_chat_btn": "💬 В чате",
        "mode_app_btn": "🚀 Открыть приложение",
        "open_app_btn": "🚀 Открыть приложение",
        "referral": "🎁 Пригласить друга",
        "referral_text": "🎁 *Реферальная программа*\n\nПригласи друга — вы оба получите +{bonus} попыток калькулятора!\n\nТвоя ссылка:\n`{link}`\n\n👥 Приглашено друзей: *{count}*",
        "referral_bonus_you": "🎉 По твоей ссылке зашёл новый пользователь!\n\nТебе начислено +{bonus} попыток калькулятора.",
        "referral_bonus_new": "🎁 Ты зашёл по приглашению! Тебе начислено +{bonus} попыток калькулятора.",
        "alert_kind_question": "Что отслеживаем?",
        "kind_price_btn": "💲 Конкретную цену",
        "kind_percent_btn": "📊 Изменение в %",
        "enter_percent": "✅ Монета: *{coin}*\n\nНа сколько % изменения уведомить? (например: `5`):",
        "percent_direction_q": "Уведомить при изменении на *{percent}%* от текущей цены (${base})\n\nВ какую сторону?",
        "grow_btn": "📈 Рост",
        "percent_suggestion_hint": "💡 Обычно эта монета двигается на ~{percent}% в день",
        "use_suggested_btn": "⚡ Использовать {percent}%",
        "drop_btn": "📉 Падение",
        "grow_text": "рост",
        "drop_text": "падение",
        "percent_alert_created": "✅ Алерт создан!\n\n📊 *{coin}* — уведомлю на {dir} *{percent}%* от текущей цены (${base})\nЦелевая цена: ${target}",
        "alert_fired_percent_suffix": "\n📊 Триггер: {dir} на {percent}% от ${base}",
        "alert_kind_price_label": "💲",
        "alert_kind_percent_label": "📊 {percent}%",
        "daily_summary_body": "📊 *Сводка портфеля*\n\nОбщая стоимость: *{symbol}{total}*\nЗа 24ч: {arrow} *{change:+.2f}%*",
        "daily_summary_open_btn": "🚀 Открыть портфель",
        "currency": "💱 Валюта",
        "choose_currency": "💱 В какой валюте показывать суммы?",
        "currency_set": "✅ Валюта отображения изменена!",
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
        "bucket_holding": "📦 Holding",
        "bucket_trading": "⚡ Trading",
        "choose_bucket": "Which bucket to add the coin to?",
        "enter_amount": "✅ Coin: *{coin}*\n\nEnter amount (e.g. `0.5`):",
        "asset_added": "✅ Added to portfolio: *{amount} {coin}*",
        "portfolio_empty": "💼 Portfolio is empty.\n\nAdd your first coin!",
        "portfolio_title": "💼 *Your portfolio:*\n\n",
        "portfolio_total": "\n💰 *Total value: {symbol}{total}*",
        "portfolio_item": "{arrow} *{coin}*: {amount} ({symbol}{value:,.2f}, {change:+.2f}%)\n",
        "remove": "❌ Remove #",
        "asset_removed": "✅ Removed from portfolio!",
        "premium_active": "💎 *Premium active*\n\nDays left: *{days}*\n\nUnlimited alerts and portfolio coins.",
        "premium_offer": "💎 *Premium*\n\n${price}/mo — unlimited alerts and portfolio coins.\n\nPay directly in crypto.",
        "get_premium": "💎 Get Premium",
        "get_premium_month": "💳 Month — ${price}",
        "get_premium_year": "🎁 Year — ${price} (save {savings}%)",
        "pay_link": "💳 Go to payment",
        "i_paid": "✅ I paid",
        "payment_created": "Invoice created for ${amount}.\n\nPay using the link below, then tap «I paid».",
        "payment_confirmed": "🎉 Payment confirmed! Premium activated for {days} days.",
        "payment_not_yet": "Payment not confirmed yet. If you just paid — wait 1-2 minutes and try again.",
        "payment_error": "Couldn't create the payment, try again later.",
        "calculator": "🧮 Calculator",
        "calc_choose_coin": "Convert from which currency?",
        "calc_enter_amount": "✅ Currency: *{coin}*\n\nEnter amount (e.g. `1.5`):",
        "calc_result_header": "🧮 *{amount} {coin} =*\n\n",
        "calc_limit_reached": "🔒 Free plan includes {limit} calculations.\n\nGet Premium for unlimited calculations.",
        "choose_mode": "👋 Hello! I'm a crypto bot.\n\nHow would you like to use it?",
        "mode_chat_btn": "💬 In chat",
        "mode_app_btn": "🚀 Open app",
        "open_app_btn": "🚀 Open app",
        "referral": "🎁 Invite a friend",
        "referral_text": "🎁 *Referral program*\n\nInvite a friend — you both get +{bonus} calculator uses!\n\nYour link:\n`{link}`\n\n👥 Friends invited: *{count}*",
        "referral_bonus_you": "🎉 Someone joined using your link!\n\nYou got +{bonus} calculator uses.",
        "referral_bonus_new": "🎁 You joined via invite! You got +{bonus} calculator uses.",
        "alert_kind_question": "What should we track?",
        "kind_price_btn": "💲 Specific price",
        "kind_percent_btn": "📊 % change",
        "enter_percent": "✅ Coin: *{coin}*\n\nNotify on what % change? (e.g. `5`):",
        "percent_direction_q": "Notify on a *{percent}%* change from current price (${base})\n\nWhich direction?",
        "grow_btn": "📈 Growth",
        "percent_suggestion_hint": "💡 This coin typically moves ~{percent}% per day",
        "use_suggested_btn": "⚡ Use {percent}%",
        "drop_btn": "📉 Drop",
        "grow_text": "growth",
        "drop_text": "drop",
        "percent_alert_created": "✅ Alert created!\n\n📊 *{coin}* — will notify on {dir} of *{percent}%* from current price (${base})\nTarget price: ${target}",
        "alert_fired_percent_suffix": "\n📊 Trigger: {dir} of {percent}% from ${base}",
        "alert_kind_price_label": "💲",
        "alert_kind_percent_label": "📊 {percent}%",
        "daily_summary_body": "📊 *Portfolio summary*\n\nTotal value: *{symbol}{total}*\n24h: {arrow} *{change:+.2f}%*",
        "daily_summary_open_btn": "🚀 Open portfolio",
        "currency": "💱 Currency",
        "choose_currency": "💱 Which currency to show amounts in?",
        "currency_set": "✅ Display currency changed!",
    },
    "uk": {
        "start": "👋 Привіт! Я крипто-бот.\n\nСлідкую за курсами, портфелем і повідомляю, коли ціна досягне потрібної позначки 🚀",
        "prices": "📊 Курси монет",
        "alerts": "🔔 Сповіщення",
        "portfolio": "💼 Портфель",
        "premium": "💎 Premium",
        "info": "ℹ️ Інформація",
        "donate": "☘️ Донат",
        "language": "🌍 Мова",
        "loading": "⏳ Завантажую курси...",
        "prices_title": "📊 *Поточні курси:*\n\n",
        "updated": "\n_Оновлено щойно_",
        "error": "❌ Помилка при завантаженні курсів. Спробуй пізніше.",
        "alerts_title": "🔔 *Сповіщення*\n\nАктивних алертів: ",
        "add_alert": "➕ Додати алерт",
        "my_alerts": "📋 Мої алерти",
        "choose_coin": "Обери монету:",
        "enter_price": "✅ Монета: *{coin}*\n\nВведи ціну в USD (наприклад: `45000`):",
        "enter_number": "❌ Введи число, наприклад: `45000`",
        "when_notify": "Ціна: *${price}*\n\nКоли повідомити?",
        "above": "📈 Вище ціни",
        "below": "📉 Нижче ціни",
        "alert_created": "✅ Алерт створено!\n\n{arrow} *{coin}* — повідомлю, коли ціна буде {dir} *${price}*",
        "above_text": "вище",
        "below_text": "нижче",
        "no_alerts": "📋 У тебе немає активних алертів.\n\nДодай перший!",
        "alerts_list": "📋 *Твої алерти:*\n\n",
        "delete": "❌ Видалити #",
        "alert_deleted": "✅ Алерт видалено!",
        "alert_fired": "🔔 *Алерт спрацював!*\n\n{arrow} *{coin}* досяг ${current}\nТвоя ціль: ${target}",
        "info_text": "ℹ️ *Про бота*\n\nСтворювач: @aquaee\nКанал: @TreckerCryptooInfo\n\nБот показує курси криптовалют, портфель і надсилає сповіщення, коли ціна досягає потрібної позначки.",
        "donate_text": "☘️ *Підтримати проєкт*\n\nTON гаманець:\n`UQArVnAPk0F6LqrGv3Zx1RPbUeW0SWeI9Ab1M9i81Fci7bKW`\n\nДякую! 🙏",
        "choose_language": "🌍 Обери мову:",
        "language_set": "✅ Мову змінено на Українську!",
        "back": "◀️ Назад",
        "limit_reached_alert": "🔒 Безкоштовно доступний {limit} алерт.\n\nОформи Premium — і алертів буде без обмежень.",
        "limit_reached_portfolio": "🔒 Безкоштовно доступна {limit} монета в портфелі.\n\nОформи Premium — і монет буде без обмежень.",
        "add_asset": "➕ Додати монету",
        "my_portfolio": "📋 Мій портфель",
        "bucket_holding": "📦 Холд",
        "bucket_trading": "⚡ Трейдинг",
        "choose_bucket": "До якої корзини додати монету?",
        "enter_amount": "✅ Монета: *{coin}*\n\nВведи кількість (наприклад: `0.5`):",
        "asset_added": "✅ Додано в портфель: *{amount} {coin}*",
        "portfolio_empty": "💼 Портфель порожній.\n\nДодай першу монету!",
        "portfolio_title": "💼 *Твій портфель:*\n\n",
        "portfolio_total": "\n💰 *Загальна вартість: {symbol}{total}*",
        "portfolio_item": "{arrow} *{coin}*: {amount} ({symbol}{value:,.2f}, {change:+.2f}%)\n",
        "remove": "❌ Прибрати #",
        "asset_removed": "✅ Прибрано з портфеля!",
        "premium_active": "💎 *Premium активний*\n\nЗалишилось днів: *{days}*\n\nБез обмежень на алерти та портфель.",
        "premium_offer": "💎 *Premium*\n\n${price}/міс — необмежені алерти та монети в портфелі.\n\nОплата в криптовалюті напряму.",
        "get_premium": "💎 Оформити Premium",
        "get_premium_month": "💳 Місяць — ${price}",
        "get_premium_year": "🎁 Рік — ${price} (вигода {savings}%)",
        "pay_link": "💳 Перейти до оплати",
        "i_paid": "✅ Я оплатив",
        "payment_created": "Рахунок створено на ${amount}.\n\nОплати за посиланням нижче, потім натисни «Я оплатив».",
        "payment_confirmed": "🎉 Оплату підтверджено! Premium активовано на {days} днів.",
        "payment_not_yet": "Оплата ще не підтверджена. Якщо щойно оплатив — почекай 1-2 хвилини і спробуй ще раз.",
        "payment_error": "Не вдалося створити платіж, спробуй пізніше.",
        "calculator": "🧮 Калькулятор",
        "calc_choose_coin": "З якої валюти рахуємо?",
        "calc_enter_amount": "✅ Валюта: *{coin}*\n\nВведи кількість (наприклад: `1.5`):",
        "calc_result_header": "🧮 *{amount} {coin} =*\n\n",
        "calc_limit_reached": "🔒 Безкоштовно доступно {limit} розрахунків.\n\nОформи Premium — і розрахунків буде без обмежень.",
        "choose_mode": "👋 Привіт! Я крипто-бот.\n\nЯк зручніше користуватись?",
        "mode_chat_btn": "💬 У чаті",
        "mode_app_btn": "🚀 Відкрити застосунок",
        "open_app_btn": "🚀 Відкрити застосунок",
        "referral": "🎁 Запросити друга",
        "referral_text": "🎁 *Реферальна програма*\n\nЗапроси друга — ви обидва отримаєте +{bonus} спроб калькулятора!\n\nТвоє посилання:\n`{link}`\n\n👥 Запрошено друзів: *{count}*",
        "referral_bonus_you": "🎉 За твоїм посиланням зайшов новий користувач!\n\nТобі нараховано +{bonus} спроб калькулятора.",
        "referral_bonus_new": "🎁 Ти зайшов за запрошенням! Тобі нараховано +{bonus} спроб калькулятора.",
        "alert_kind_question": "Що відстежуємо?",
        "kind_price_btn": "💲 Конкретну ціну",
        "kind_percent_btn": "📊 Зміну у %",
        "enter_percent": "✅ Монета: *{coin}*\n\nНа скільки % зміни повідомити? (наприклад: `5`):",
        "percent_direction_q": "Повідомити при зміні на *{percent}%* від поточної ціни (${base})\n\nУ який бік?",
        "grow_btn": "📈 Зростання",
        "percent_suggestion_hint": "💡 Ця монета зазвичай рухається на ~{percent}% на день",
        "use_suggested_btn": "⚡ Використати {percent}%",
        "drop_btn": "📉 Падіння",
        "grow_text": "зростання",
        "drop_text": "падіння",
        "percent_alert_created": "✅ Алерт створено!\n\n📊 *{coin}* — повідомлю на {dir} *{percent}%* від поточної ціни (${base})\nЦільова ціна: ${target}",
        "alert_fired_percent_suffix": "\n📊 Тригер: {dir} на {percent}% від ${base}",
        "alert_kind_price_label": "💲",
        "alert_kind_percent_label": "📊 {percent}%",
        "daily_summary_body": "📊 *Зведення портфеля*\n\nЗагальна вартість: *{symbol}{total}*\nЗа 24г: {arrow} *{change:+.2f}%*",
        "daily_summary_open_btn": "🚀 Відкрити портфель",
        "currency": "💱 Валюта",
        "choose_currency": "💱 В якій валюті показувати суми?",
        "currency_set": "✅ Валюту відображення змінено!",
    }
}


def t(user_id, key):
    lang = db.get_language(user_id)
    return TEXTS[lang][key]


class AlertState(StatesGroup):
    waiting_coin = State()
    waiting_kind = State()
    waiting_price = State()
    waiting_direction = State()
    waiting_percent = State()
    waiting_percent_direction = State()


class PortfolioState(StatesGroup):
    waiting_bucket = State()
    waiting_coin = State()
    waiting_amount = State()


class CalcState(StatesGroup):
    waiting_coin = State()
    waiting_amount = State()


class AdminState(StatesGroup):
    waiting_password = State()
    waiting_grant = State()


def is_unlimited(uid: int) -> bool:
    """Админы и Premium-юзеры не упираются в бесплатные лимиты."""
    return uid in admin_ids or db.is_premium(uid)


def main_keyboard(user_id):
    rows = [
        [KeyboardButton(text=t(user_id, "prices")), KeyboardButton(text=t(user_id, "alerts"))],
        [KeyboardButton(text=t(user_id, "portfolio")), KeyboardButton(text=t(user_id, "calculator"))],
        [KeyboardButton(text=t(user_id, "premium")), KeyboardButton(text=t(user_id, "referral"))],
        [KeyboardButton(text=t(user_id, "info")), KeyboardButton(text=t(user_id, "donate"))],
        [KeyboardButton(text=t(user_id, "language")), KeyboardButton(text=t(user_id, "currency"))],
    ]
    if MINI_APP_URL:
        rows.append([KeyboardButton(text=t(user_id, "open_app_btn"), web_app=WebAppInfo(url=MINI_APP_URL))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🎟 Выдать попытки калькулятора", callback_data="admin_grant")],
        [InlineKeyboardButton(text="📢 Рассылка всем", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="❌ Выйти из админки", callback_data="admin_exit")],
    ])


def update_user_stats(user_id, username=None):
    db.get_or_create_user(user_id, username)


# ─── /start ───
@dp.message(CommandStart())
async def start(message: Message):
    uid = message.from_user.id
    username = message.from_user.username or ""
    is_new = not db.user_exists(uid)
    update_user_stats(uid, username)
    if username in ADMIN_USERNAMES:
        admin_ids.add(uid)

    # Реферальная ссылка: /start ref_<referrer_id> — бонус только для по-настоящему новых юзеров
    if is_new:
        parts = message.text.split(maxsplit=1)
        if len(parts) == 2 and parts[1].startswith("ref_"):
            try:
                referrer_id = int(parts[1].replace("ref_", ""))
            except ValueError:
                referrer_id = None
            if referrer_id and db.link_referral(referrer_id, uid):
                db.grant_calc_attempts(referrer_id, REFERRAL_BONUS)
                db.grant_calc_attempts(uid, REFERRAL_BONUS)
                try:
                    await bot.send_message(
                        referrer_id,
                        t(referrer_id, "referral_bonus_you").format(bonus=REFERRAL_BONUS),
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
                await message.answer(t(uid, "referral_bonus_new").format(bonus=REFERRAL_BONUS), parse_mode="Markdown")

    buttons = [[InlineKeyboardButton(text=t(uid, "mode_chat_btn"), callback_data="mode_chat")]]
    if MINI_APP_URL:
        buttons.append([InlineKeyboardButton(text=t(uid, "mode_app_btn"), web_app=WebAppInfo(url=MINI_APP_URL))])
    await message.answer(t(uid, "choose_mode"), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data == "mode_chat")
async def mode_chat_cb(call: CallbackQuery):
    uid = call.from_user.id
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer()
    await call.message.answer(t(uid, "start"), reply_markup=main_keyboard(uid))


# ─── Рефералка ───
@dp.message(F.text.in_(["🎁 Пригласить друга", "🎁 Invite a friend", "🎁 Запросити друга"]))
async def referral_menu(message: Message):
    uid = message.from_user.id
    update_user_stats(uid)
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}" if BOT_USERNAME else "—"
    count = db.referral_count(uid)
    await message.answer(
        t(uid, "referral_text").format(bonus=REFERRAL_BONUS, link=link, count=count),
        parse_mode="Markdown"
    )


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


# ─── Админ: выдать попытки калькулятора ───
@dp.callback_query(F.data == "admin_grant")
async def admin_grant_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in admin_ids:
        await call.answer("❌ Нет доступа!", show_alert=True)
        return
    await call.message.edit_text(
        "🎟 Введи ID пользователя и количество попыток через пробел, например:\n`123456789 10`\n\n"
        "Юзера можно указать, даже если он ещё не запускал бота — попытки применятся, когда он это сделает.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")]
        ])
    )
    await state.set_state(AdminState.waiting_grant)


@dp.message(AdminState.waiting_grant)
async def admin_grant_process(message: Message, state: FSMContext):
    if message.from_user.id not in admin_ids:
        await state.clear()
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].lstrip("-").isdigit():
        await message.answer("❌ Формат: `ID количество`, например: `123456789 10`", parse_mode="Markdown")
        return
    target_uid = int(parts[0])
    amount = int(parts[1])
    new_total = db.grant_calc_attempts(target_uid, amount)
    await state.clear()
    await message.answer(
        f"✅ Выдано {amount} попыток пользователю `{target_uid}`.\nВсего бонусных попыток у него: *{new_total}*",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
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
@dp.message(F.text.in_(["📊 Курсы монет", "📊 Prices", "📊 Курси монет"]))
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
            text += f"{arrow} *{display_coin(symbol)}*: ${price:,.2f}  ({change:+.2f}%)\n"
        text += t(uid, "updated")
        await message.answer(text, parse_mode="Markdown")
    except Exception:
        await message.answer(t(uid, "error"))


# ─── Уведомления ───
@dp.message(F.text.in_(["🔔 Уведомления", "🔔 Alerts", "🔔 Сповіщення"]))
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
    if not is_unlimited(uid) and db.count_alerts(uid) >= FREE_ALERT_LIMIT:
        await call.message.edit_text(
            t(uid, "limit_reached_alert").format(limit=FREE_ALERT_LIMIT),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(uid, "get_premium"), callback_data="premium_buy")],
            ])
        )
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=display_coin(s), callback_data=f"coin_{s}") for s in list(COINS.keys())[:3]],
        [InlineKeyboardButton(text=display_coin(s), callback_data=f"coin_{s}") for s in list(COINS.keys())[3:]],
    ])
    await call.message.edit_text(t(uid, "choose_coin"), reply_markup=keyboard)
    await state.set_state(AlertState.waiting_coin)


@dp.callback_query(F.data.startswith("coin_"))
async def add_alert_step2(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    coin = call.data.replace("coin_", "")
    await state.update_data(coin=coin)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid, "kind_price_btn"), callback_data="akind_price")],
        [InlineKeyboardButton(text=t(uid, "kind_percent_btn"), callback_data="akind_percent")],
    ])
    await call.message.edit_text(t(uid, "alert_kind_question"), reply_markup=keyboard)
    await state.set_state(AlertState.waiting_kind)


@dp.callback_query(F.data.in_(["akind_price", "akind_percent"]))
async def add_alert_step_kind(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    data = await state.get_data()
    coin = data["coin"]
    if call.data == "akind_price":
        await call.message.edit_text(t(uid, "enter_price").format(coin=display_coin(coin)), parse_mode="Markdown")
        await state.set_state(AlertState.waiting_price)
    else:
        coin_id = COINS.get(coin)
        suggested = await get_suggested_alert_percent(coin_id) if coin_id else 5.0
        text = t(uid, "enter_percent").format(coin=display_coin(coin))
        text += "\n\n" + t(uid, "percent_suggestion_hint").format(percent=suggested)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(uid, "use_suggested_btn").format(percent=suggested), callback_data=f"usesugg_{suggested}")],
        ])
        await call.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        await state.set_state(AlertState.waiting_percent)


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
    db.add_alert(uid, data["coin"], data["price"], direction, kind="price")
    arrow = "📈" if direction == "above" else "📉"
    dir_text = t(uid, "above_text") if direction == "above" else t(uid, "below_text")
    await call.message.edit_text(
        t(uid, "alert_created").format(arrow=arrow, coin=display_coin(data["coin"]), dir=dir_text, price=f"{data['price']:,.2f}"),
        parse_mode="Markdown"
    )
    await state.clear()


async def _ask_percent_direction(uid, coin, percent, state, answer_func):
    coin_id = COINS.get(coin)
    try:
        prices = await get_prices()
    except Exception:
        await answer_func(t(uid, "error"))
        await state.clear()
        return
    if not coin_id or coin_id not in prices:
        await answer_func(t(uid, "error"))
        await state.clear()
        return
    base_price = prices[coin_id]["usd"]
    await state.update_data(percent=percent, base_price=base_price)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid, "grow_btn"), callback_data="pdir_up")],
        [InlineKeyboardButton(text=t(uid, "drop_btn"), callback_data="pdir_down")],
    ])
    await answer_func(
        t(uid, "percent_direction_q").format(percent=percent, base=f"{base_price:,.2f}"),
        parse_mode="Markdown", reply_markup=keyboard
    )
    await state.set_state(AlertState.waiting_percent_direction)


@dp.message(AlertState.waiting_percent)
async def add_alert_percent_step(message: Message, state: FSMContext):
    uid = message.from_user.id
    try:
        percent = float(message.text.replace(",", ".").replace("%", ""))
    except ValueError:
        await message.answer(t(uid, "enter_number"), parse_mode="Markdown")
        return
    if percent <= 0:
        await message.answer(t(uid, "enter_number"), parse_mode="Markdown")
        return
    data = await state.get_data()
    await _ask_percent_direction(uid, data["coin"], percent, state, message.answer)


@dp.callback_query(F.data.startswith("usesugg_"))
async def use_suggested_percent(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    percent = float(call.data.replace("usesugg_", ""))
    data = await state.get_data()

    async def answer_func(text, **kwargs):
        await call.message.edit_text(text, **kwargs)

    await _ask_percent_direction(uid, data["coin"], percent, state, answer_func)


@dp.callback_query(F.data.in_(["pdir_up", "pdir_down"]))
async def add_alert_percent_final(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    data = await state.get_data()
    coin, percent, base_price = data["coin"], data["percent"], data["base_price"]

    if call.data == "pdir_up":
        target_price = base_price * (1 + percent / 100)
        direction = "above"
        dir_text = t(uid, "grow_text")
        arrow = "📈"
    else:
        target_price = base_price * (1 - percent / 100)
        direction = "below"
        dir_text = t(uid, "drop_text")
        arrow = "📉"

    db.add_alert(uid, coin, target_price, direction, kind="percent", percent=percent, base_price=base_price)
    await call.message.edit_text(
        t(uid, "percent_alert_created").format(
            coin=display_coin(coin), dir=dir_text, percent=percent,
            base=f"{base_price:,.2f}", target=f"{target_price:,.2f}"
        ),
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
        if a["kind"] == "percent" and a["percent"] is not None:
            dir_text = t(uid, "grow_text") if a["direction"] == "above" else t(uid, "drop_text")
            label = t(uid, "alert_kind_percent_label").format(percent=a["percent"])
            text += f"{arrow} *{display_coin(a['coin'])}* {label} ({dir_text}, ${a['price']:,.2f})\n"
        else:
            dir_text = t(uid, "above_text") if a["direction"] == "above" else t(uid, "below_text")
            text += f"{arrow} *{display_coin(a['coin'])}* {dir_text} ${a['price']:,.2f}\n"
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
        [InlineKeyboardButton(text=t(uid, "bucket_holding"), callback_data="my_portfolio_holding")],
        [InlineKeyboardButton(text=t(uid, "bucket_trading"), callback_data="my_portfolio_trading")],
    ])
    await message.answer(t(uid, "portfolio"), reply_markup=keyboard)


@dp.callback_query(F.data == "add_asset")
async def add_asset_step1(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_unlimited(uid) and db.count_portfolio(uid) >= FREE_PORTFOLIO_LIMIT:
        await call.message.edit_text(
            t(uid, "limit_reached_portfolio").format(limit=FREE_PORTFOLIO_LIMIT),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(uid, "get_premium"), callback_data="premium_buy")],
            ])
        )
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid, "bucket_holding"), callback_data="bucket_holding")],
        [InlineKeyboardButton(text=t(uid, "bucket_trading"), callback_data="bucket_trading")],
    ])
    await call.message.edit_text(t(uid, "choose_bucket"), reply_markup=keyboard)
    await state.set_state(PortfolioState.waiting_bucket)


@dp.callback_query(F.data.in_(["bucket_holding", "bucket_trading"]))
async def add_asset_step_bucket(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    bucket = "holding" if call.data == "bucket_holding" else "trading"
    await state.update_data(bucket=bucket)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=display_coin(s), callback_data=f"pcoin_{s}") for s in list(COINS.keys())[:3]],
        [InlineKeyboardButton(text=display_coin(s), callback_data=f"pcoin_{s}") for s in list(COINS.keys())[3:]],
    ])
    await call.message.edit_text(t(uid, "choose_coin"), reply_markup=keyboard)
    await state.set_state(PortfolioState.waiting_coin)


@dp.callback_query(F.data.startswith("pcoin_"))
async def add_asset_step2(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    coin = call.data.replace("pcoin_", "")
    await state.update_data(coin=coin)
    await call.message.edit_text(t(uid, "enter_amount").format(coin=display_coin(coin)), parse_mode="Markdown")
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
    bucket = data.get("bucket", "holding")
    db.add_portfolio_item(uid, data["coin"], amount, bucket=bucket)
    await message.answer(t(uid, "asset_added").format(amount=amount, coin=display_coin(data["coin"])), parse_mode="Markdown")
    await state.clear()


@dp.callback_query(F.data.in_(["my_portfolio_holding", "my_portfolio_trading"]))
async def show_portfolio(call: CallbackQuery):
    uid = call.from_user.id
    bucket = "holding" if call.data == "my_portfolio_holding" else "trading"
    await _render_portfolio_bucket(call, uid, bucket)


async def _render_portfolio_bucket(call: CallbackQuery, uid: int, bucket: str):
    items = db.get_portfolio(uid, bucket=bucket)
    if not items:
        await call.message.edit_text(t(uid, "portfolio_empty"))
        return
    try:
        prices = await get_prices()
    except Exception:
        await call.message.edit_text(t(uid, "error"))
        return

    currency = db.get_currency(uid)
    symbol = CURRENCY_SYMBOLS.get(currency, "$")
    bucket_label = t(uid, "bucket_holding") if bucket == "holding" else t(uid, "bucket_trading")
    text = t(uid, "portfolio_title") + f"_{bucket_label}_\n\n"
    buttons = []
    total = 0.0
    for item in items:
        coin_id = COINS.get(item["coin"])
        if not coin_id or coin_id not in prices:
            continue
        price = prices[coin_id].get(currency, prices[coin_id]["usd"])
        change = prices[coin_id]["usd_24h_change"]
        value = price * item["amount"]
        total += value
        arrow = "🟢" if change >= 0 else "🔴"
        text += t(uid, "portfolio_item").format(arrow=arrow, coin=display_coin(item["coin"]), amount=item["amount"], symbol=symbol, value=value, change=change)
        buttons.append([InlineKeyboardButton(text=t(uid, "remove") + str(item["id"]), callback_data=f"prem_{item['id']}_{bucket}")])
    text += t(uid, "portfolio_total").format(symbol=symbol, total=f"{total:,.2f}")
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("prem_"))
async def remove_asset_cb(call: CallbackQuery):
    uid = call.from_user.id
    payload = call.data.replace("prem_", "")
    item_id_str, _, bucket = payload.partition("_")
    item_id = int(item_id_str)
    db.remove_portfolio_item(uid, item_id)
    await call.answer(t(uid, "asset_removed"))
    await _render_portfolio_bucket(call, uid, bucket or "holding")


# ─── Калькулятор ───
@dp.message(F.text.in_(["🧮 Калькулятор", "🧮 Calculator"]))
async def calculator_menu(message: Message, state: FSMContext):
    uid = message.from_user.id
    update_user_stats(uid)
    used, bonus = db.get_calc_status(uid)
    limit = FREE_CALC_LIMIT + bonus
    if not is_unlimited(uid) and used >= limit:
        await message.answer(
            t(uid, "calc_limit_reached").format(limit=limit),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(uid, "get_premium"), callback_data="premium_buy")],
            ])
        )
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=display_coin(s), callback_data=f"calc_{s}") for s in list(COINS.keys())[:3]],
        [InlineKeyboardButton(text=display_coin(s), callback_data=f"calc_{s}") for s in list(COINS.keys())[3:]],
    ])
    await message.answer(t(uid, "calc_choose_coin"), reply_markup=keyboard)
    await state.set_state(CalcState.waiting_coin)


@dp.callback_query(F.data.startswith("calc_"))
async def calc_step2(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    coin = call.data.replace("calc_", "")
    await state.update_data(coin=coin)
    await call.message.edit_text(t(uid, "calc_enter_amount").format(coin=display_coin(coin)), parse_mode="Markdown")
    await state.set_state(CalcState.waiting_amount)


@dp.message(CalcState.waiting_amount)
async def calc_step3(message: Message, state: FSMContext):
    uid = message.from_user.id
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer(t(uid, "enter_number"), parse_mode="Markdown")
        return

    data = await state.get_data()
    coin = data["coin"]
    coin_id = COINS.get(coin)

    try:
        prices = await get_prices()
    except Exception:
        await message.answer(t(uid, "error"))
        await state.clear()
        return

    if not coin_id or coin_id not in prices:
        await message.answer(t(uid, "error"))
        await state.clear()
        return

    usd_value = amount * prices[coin_id]["usd"]
    text = t(uid, "calc_result_header").format(amount=amount, coin=display_coin(coin))
    text += f"💵 USD: ${usd_value:,.2f}\n"
    for symbol, cid in COINS.items():
        if symbol == coin or cid not in prices:
            continue
        converted = usd_value / prices[cid]["usd"]
        text += f"• {display_coin(symbol)}: {converted:,.6f}\n"

    if not is_unlimited(uid):
        db.increment_calc_used(uid)

    await message.answer(text, parse_mode="Markdown")
    await state.clear()


# ─── Premium ───
@dp.message(F.text.in_(["💎 Premium"]))
async def premium_menu(message: Message):
    uid = message.from_user.id
    update_user_stats(uid)
    if db.is_premium(uid):
        days = db.premium_days_left(uid)
        await message.answer(t(uid, "premium_active").format(days=days), parse_mode="Markdown")
        return
    yearly_monthly_equiv = PREMIUM_PRICE_USD * 12
    savings = round(100 - (PREMIUM_YEARLY_PRICE_USD / yearly_monthly_equiv * 100)) if yearly_monthly_equiv else 0
    await message.answer(
        t(uid, "premium_offer").format(price=PREMIUM_PRICE_USD),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(uid, "get_premium_month").format(price=PREMIUM_PRICE_USD), callback_data="premium_buy_month")],
            [InlineKeyboardButton(text=t(uid, "get_premium_year").format(price=PREMIUM_YEARLY_PRICE_USD, savings=savings), callback_data="premium_buy_year")],
        ])
    )


@dp.callback_query(F.data == "premium_buy")
async def show_premium_plans(call: CallbackQuery):
    uid = call.from_user.id
    yearly_monthly_equiv = PREMIUM_PRICE_USD * 12
    savings = round(100 - (PREMIUM_YEARLY_PRICE_USD / yearly_monthly_equiv * 100)) if yearly_monthly_equiv else 0
    await call.message.edit_text(
        t(uid, "premium_offer").format(price=PREMIUM_PRICE_USD),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(uid, "get_premium_month").format(price=PREMIUM_PRICE_USD), callback_data="premium_buy_month")],
            [InlineKeyboardButton(text=t(uid, "get_premium_year").format(price=PREMIUM_YEARLY_PRICE_USD, savings=savings), callback_data="premium_buy_year")],
        ])
    )


@dp.callback_query(F.data.in_(["premium_buy_month", "premium_buy_year"]))
async def premium_buy(call: CallbackQuery):
    uid = call.from_user.id
    is_yearly = call.data == "premium_buy_year"
    amount = PREMIUM_YEARLY_PRICE_USD if is_yearly else PREMIUM_PRICE_USD
    days = PREMIUM_YEARLY_DAYS if is_yearly else PREMIUM_DAYS
    order_id = f"{uid}-{uuid.uuid4().hex[:8]}"
    try:
        invoice = payments.create_invoice(
            amount_usd=amount,
            order_id=order_id,
            description=f"Premium {days}d for user {uid}",
        )
    except Exception:
        await call.answer(t(uid, "payment_error"), show_alert=True)
        return

    payment_id = str(invoice.get("id") or invoice.get("payment_id") or order_id)
    invoice_url = invoice.get("invoice_url")
    db.create_payment_record(payment_id, uid, amount, plan_days=days)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid, "pay_link"), url=invoice_url)],
        [InlineKeyboardButton(text=t(uid, "i_paid"), callback_data=f"checkpay_{payment_id}")],
    ])
    await call.message.edit_text(
        t(uid, "payment_created").format(amount=amount),
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
        payment_row = db.get_payment(payment_id)
        days = payment_row["plan_days"] if payment_row else PREMIUM_DAYS
        db.update_payment_status(payment_id, "finished")
        db.activate_premium(uid, days)
        await call.message.edit_text(t(uid, "payment_confirmed").format(days=days), parse_mode="Markdown")
    else:
        await call.answer(t(uid, "payment_not_yet"), show_alert=True)


# ─── Инфо ───
@dp.message(F.text.in_(["ℹ️ Информация", "ℹ️ Info", "ℹ️ Інформація"]))
async def info(message: Message):
    update_user_stats(message.from_user.id)
    await message.answer(t(message.from_user.id, "info_text"), parse_mode="Markdown")


# ─── Донат ───
@dp.message(F.text.in_(["☘️ Донат", "☘️ Donate"]))
async def donate(message: Message):
    update_user_stats(message.from_user.id)
    await message.answer(t(message.from_user.id, "donate_text"), parse_mode="Markdown")


# ─── Язык ───
@dp.message(F.text.in_(["🌍 Язык", "🌍 Language", "🌍 Мова"]))
async def language_menu(message: Message):
    update_user_stats(message.from_user.id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang_uk")],
    ])
    await message.answer(t(message.from_user.id, "choose_language"), reply_markup=keyboard)


@dp.callback_query(F.data.startswith("lang_"))
async def set_language(call: CallbackQuery):
    uid = call.from_user.id
    lang = call.data.replace("lang_", "")
    db.set_language(uid, lang)
    await call.message.edit_text(t(uid, "language_set"))
    await call.message.answer(t(uid, "start"), reply_markup=main_keyboard(uid))


# ─── Валюта отображения ───
@dp.message(F.text.in_(["💱 Валюта", "💱 Currency"]))
async def currency_menu(message: Message):
    uid = message.from_user.id
    update_user_stats(uid)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 USD", callback_data="cur_usd")],
        [InlineKeyboardButton(text="🇺🇦 UAH (₴)", callback_data="cur_uah")],
        [InlineKeyboardButton(text="💶 EUR (€)", callback_data="cur_eur")],
    ])
    await message.answer(t(uid, "choose_currency"), reply_markup=keyboard)


@dp.callback_query(F.data.startswith("cur_"))
async def set_currency(call: CallbackQuery):
    uid = call.from_user.id
    currency = call.data.replace("cur_", "")
    db.set_currency(uid, currency)
    await call.message.edit_text(t(uid, "currency_set"))


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
                        fired_text = t(uid, "alert_fired").format(
                            arrow=arrow,
                            coin=display_coin(alert["coin"]),
                            current=f"{current_price:,.2f}",
                            target=f"{alert['price']:,.2f}"
                        )
                        if alert["kind"] == "percent" and alert["percent"] is not None:
                            dir_text = t(uid, "grow_text") if alert["direction"] == "above" else t(uid, "drop_text")
                            fired_text += t(uid, "alert_fired_percent_suffix").format(
                                dir=dir_text, percent=alert["percent"], base=f"{alert['base_price']:,.2f}"
                            )
                        await bot.send_message(uid, fired_text, parse_mode="Markdown")
                    except Exception:
                        pass
                    db.log_fired_alert(uid, alert["coin"], fired_text)
                    db.delete_alert_by_id(alert["id"])
        except Exception:
            pass


async def send_daily_summaries():
    today = time.strftime("%Y-%m-%d")
    try:
        prices = await get_prices()
    except Exception:
        return

    for uid in db.users_for_daily_summary(today):
        items = db.get_portfolio(uid)
        if not items:
            db.mark_summary_sent(uid, today)
            continue

        currency = db.get_currency(uid)
        total = 0.0
        weighted_change = 0.0
        usd_weight = 0.0
        for item in items:
            coin_id = COINS.get(item["coin"])
            if not coin_id or coin_id not in prices:
                continue
            price_in_currency = prices[coin_id].get(currency)
            price_usd = prices[coin_id].get("usd")
            change = prices[coin_id].get("usd_24h_change", 0) or 0
            if price_in_currency is None or price_usd is None:
                continue
            total += price_in_currency * item["amount"]
            usd_value = price_usd * item["amount"]
            weighted_change += change * usd_value
            usd_weight += usd_value

        db.mark_summary_sent(uid, today)
        if usd_weight == 0:
            continue

        avg_change = weighted_change / usd_weight
        symbol = CURRENCY_SYMBOLS.get(currency, "$")
        arrow = "📈" if avg_change >= 0 else "📉"
        text = t(uid, "daily_summary_body").format(symbol=symbol, total=f"{total:,.2f}", arrow=arrow, change=avg_change)

        kb = None
        if MINI_APP_URL:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(uid, "daily_summary_open_btn"), web_app=WebAppInfo(url=MINI_APP_URL))]
            ])
        try:
            await bot.send_message(uid, text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass


async def daily_summary_loop():
    while True:
        now = datetime.now(timezone.utc)
        target = now.replace(hour=DAILY_SUMMARY_HOUR_UTC, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        try:
            await send_daily_summaries()
        except Exception:
            logging.exception("Ошибка при отправке ежедневной сводки")


async def run_api_server():
    """Поднимает веб-сервер для Mini App на порту, который даёт Railway (или 8000 локально)."""
    import uvicorn
    from api import app as api_app
    port = int(os.getenv("PORT", "8000"))
    config = uvicorn.Config(api_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    global BOT_USERNAME
    db.init_db()
    me = await bot.get_me()
    BOT_USERNAME = me.username
    asyncio.create_task(check_alerts())
    asyncio.create_task(daily_summary_loop())
    # Веб-сервер поднимаем всегда — Railway (как web-сервис) должен видеть открытый порт
    # с самого первого деплоя, иначе решит, что деплой не удался.
    # Кнопка на Mini App в самом боте появится отдельно, как только пропишешь MINI_APP_URL.
    await asyncio.gather(
        dp.start_polling(bot),
        run_api_server(),
    )


if __name__ == "__main__":
    asyncio.run(main())
