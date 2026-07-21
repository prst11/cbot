import os
import sqlite3
import time
from contextlib import contextmanager

# На Railway укажи DB_PATH=/data/bot.db и подключи Volume с mount path /data —
# иначе база будет стираться при каждом деплое (файловая система Railway без Volume не постоянна)
DB_PATH = os.getenv("DB_PATH", "bot.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                lang TEXT NOT NULL DEFAULT 'ru',
                premium_until INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                last_seen_date TEXT NOT NULL,
                calc_used INTEGER NOT NULL DEFAULT 0,
                calc_bonus INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL UNIQUE,
                created_at INTEGER NOT NULL
            )
        """)
        for coldef in [
            "calc_used INTEGER NOT NULL DEFAULT 0",
            "calc_bonus INTEGER NOT NULL DEFAULT 0",
            "last_seen_ts INTEGER NOT NULL DEFAULT 0",
        ]:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {coldef}")
            except sqlite3.OperationalError:
                pass  # колонка уже есть
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                coin TEXT NOT NULL,
                price REAL NOT NULL,
                direction TEXT NOT NULL
            )
        """)
        for coldef in [
            "kind TEXT NOT NULL DEFAULT 'price'",
            "percent REAL",
            "base_price REAL",
        ]:
            try:
                conn.execute(f"ALTER TABLE alerts ADD COLUMN {coldef}")
            except sqlite3.OperationalError:
                pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                coin TEXT NOT NULL,
                amount REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount_usd REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'waiting',
                created_at INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                coin TEXT NOT NULL,
                UNIQUE(user_id, coin)
            )
        """)


def _today():
    return time.strftime("%Y-%m-%d")


# ─── Пользователи ───
def user_exists(user_id: int) -> bool:
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone() is not None


def get_or_create_user(user_id: int, username: str | None) -> sqlite3.Row:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        now = int(time.time())
        if row is None:
            conn.execute(
                "INSERT INTO users (user_id, username, lang, premium_until, created_at, last_seen_date, last_seen_ts) "
                "VALUES (?, ?, 'ru', 0, ?, ?, ?)",
                (user_id, username, now, _today(), now),
            )
        else:
            conn.execute(
                "UPDATE users SET username = ?, last_seen_date = ?, last_seen_ts = ? WHERE user_id = ?",
                (username, _today(), now, user_id),
            )
        return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


def set_language(user_id: int, lang: str):
    with get_conn() as conn:
        conn.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id))


def get_language(user_id: int) -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row["lang"] if row else "ru"


def is_premium(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT premium_until FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row and row["premium_until"] > int(time.time()))


def premium_days_left(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT premium_until FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row or row["premium_until"] <= int(time.time()):
            return 0
        return max(0, (row["premium_until"] - int(time.time())) // 86400)


def activate_premium(user_id: int, days: int) -> int:
    with get_conn() as conn:
        now = int(time.time())
        row = conn.execute("SELECT premium_until FROM users WHERE user_id = ?", (user_id,)).fetchone()
        base = row["premium_until"] if row and row["premium_until"] > now else now
        new_until = base + days * 86400
        conn.execute("UPDATE users SET premium_until = ? WHERE user_id = ?", (new_until, user_id))
        return new_until


# ─── Алерты ───
def count_alerts(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) c FROM alerts WHERE user_id = ?", (user_id,)).fetchone()
        return row["c"]


def add_alert(user_id: int, coin: str, price: float, direction: str, kind: str = "price", percent: float | None = None, base_price: float | None = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO alerts (user_id, coin, price, direction, kind, percent, base_price) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, coin, price, direction, kind, percent, base_price),
        )


def get_alerts(user_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM alerts WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()


def delete_alert(user_id: int, alert_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM alerts WHERE id = ? AND user_id = ?", (alert_id, user_id))


def get_all_alerts() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM alerts").fetchall()


def delete_alert_by_id(alert_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))


# ─── Портфель ───
def count_portfolio(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) c FROM portfolio WHERE user_id = ?", (user_id,)).fetchone()
        return row["c"]


def get_portfolio(user_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM portfolio WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()


def add_portfolio_item(user_id: int, coin: str, amount: float):
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, amount FROM portfolio WHERE user_id = ? AND coin = ?", (user_id, coin)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE portfolio SET amount = ? WHERE id = ?",
                (existing["amount"] + amount, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO portfolio (user_id, coin, amount) VALUES (?, ?, ?)",
                (user_id, coin, amount),
            )


def remove_portfolio_item(user_id: int, item_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM portfolio WHERE id = ? AND user_id = ?", (item_id, user_id))


# ─── Попытки калькулятора ───
def get_calc_status(user_id: int) -> tuple[int, int]:
    with get_conn() as conn:
        row = conn.execute("SELECT calc_used, calc_bonus FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return 0, 0
        return row["calc_used"], row["calc_bonus"]


def increment_calc_used(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE users SET calc_used = calc_used + 1 WHERE user_id = ?", (user_id,))


def grant_calc_attempts(user_id: int, amount: int) -> int:
    """Добавляет бонусные попытки калькулятора юзеру (создаёт юзера, если его ещё нет в базе)."""
    with get_conn() as conn:
        exists = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO users (user_id, username, lang, premium_until, created_at, last_seen_date, calc_used, calc_bonus) "
                "VALUES (?, NULL, 'ru', 0, ?, ?, 0, ?)",
                (user_id, int(time.time()), _today(), amount),
            )
        else:
            conn.execute("UPDATE users SET calc_bonus = calc_bonus + ? WHERE user_id = ?", (amount, user_id))
        row = conn.execute("SELECT calc_bonus FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row["calc_bonus"]


# ─── Реферальная программа ───
def link_referral(referrer_id: int, referred_id: int) -> bool:
    """Возвращает True, если связь успешно создана (юзер ещё не был кем-то приглашён)."""
    if referrer_id == referred_id:
        return False
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)",
                (referrer_id, referred_id, int(time.time())),
            )
            return True
        except sqlite3.IntegrityError:
            return False  # этот юзер уже был кем-то приглашён раньше


def referral_count(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) c FROM referrals WHERE referrer_id = ?", (user_id,)).fetchone()
        return row["c"]


def was_referred(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM referrals WHERE referred_id = ?", (user_id,)).fetchone()
        return row is not None


# ─── Платежи ───
def create_payment_record(payment_id: str, user_id: int, amount_usd: float):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO payments (payment_id, user_id, amount_usd, status, created_at) "
            "VALUES (?, ?, ?, 'waiting', ?)",
            (payment_id, user_id, amount_usd, int(time.time())),
        )


def update_payment_status(payment_id: str, status: str):
    with get_conn() as conn:
        conn.execute("UPDATE payments SET status = ? WHERE payment_id = ?", (status, payment_id))


# ─── Избранное (watchlist) ───
def get_watchlist(user_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT coin FROM watchlist WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()
        return [r["coin"] for r in rows]


def add_to_watchlist(user_id: int, coin: str):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO watchlist (user_id, coin) VALUES (?, ?)", (user_id, coin))


def remove_from_watchlist(user_id: int, coin: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM watchlist WHERE user_id = ? AND coin = ?", (user_id, coin))


# ─── Статистика для админки ───
def online_count(threshold_seconds: int = 300) -> int:
    with get_conn() as conn:
        cutoff = int(time.time()) - threshold_seconds
        row = conn.execute("SELECT COUNT(*) c FROM users WHERE last_seen_ts >= ?", (cutoff,)).fetchone()
        return row["c"]


def online_users(threshold_seconds: int = 300, limit: int = 50) -> list[sqlite3.Row]:
    with get_conn() as conn:
        cutoff = int(time.time()) - threshold_seconds
        return conn.execute(
            "SELECT user_id, username, last_seen_ts, premium_until FROM users "
            "WHERE last_seen_ts >= ? ORDER BY last_seen_ts DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()


def stats_summary() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        active_today = conn.execute(
            "SELECT COUNT(*) c FROM users WHERE last_seen_date = ?", (_today(),)
        ).fetchone()["c"]
        premium = conn.execute(
            "SELECT COUNT(*) c FROM users WHERE premium_until > ?", (int(time.time()),)
        ).fetchone()["c"]
        with_alerts = conn.execute("SELECT COUNT(DISTINCT user_id) c FROM alerts").fetchone()["c"]
        total_alerts = conn.execute("SELECT COUNT(*) c FROM alerts").fetchone()["c"]
        ru_users = conn.execute("SELECT COUNT(*) c FROM users WHERE lang = 'ru'").fetchone()["c"]
        en_users = conn.execute("SELECT COUNT(*) c FROM users WHERE lang = 'en'").fetchone()["c"]
        uk_users = conn.execute("SELECT COUNT(*) c FROM users WHERE lang = 'uk'").fetchone()["c"]
        cutoff = int(time.time()) - 300
        online = conn.execute("SELECT COUNT(*) c FROM users WHERE last_seen_ts >= ?", (cutoff,)).fetchone()["c"]
        return {
            "total": total,
            "active_today": active_today,
            "online": online,
            "premium": premium,
            "with_alerts": with_alerts,
            "total_alerts": total_alerts,
            "ru_users": ru_users,
            "en_users": en_users,
            "uk_users": uk_users,
        }


def all_user_ids() -> list[int]:
    with get_conn() as conn:
        return [r["user_id"] for r in conn.execute("SELECT user_id FROM users").fetchall()]
