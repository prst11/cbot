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
        # миграция для баз, созданных до появления полей калькулятора
        for coldef in ["calc_used INTEGER NOT NULL DEFAULT 0", "calc_bonus INTEGER NOT NULL DEFAULT 0"]:
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


def _today():
    return time.strftime("%Y-%m-%d")


# ─── Пользователи ───
def get_or_create_user(user_id: int, username: str | None) -> sqlite3.Row:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (user_id, username, lang, premium_until, created_at, last_seen_date) "
                "VALUES (?, ?, 'ru', 0, ?, ?)",
                (user_id, username, int(time.time()), _today()),
            )
        else:
            conn.execute(
                "UPDATE users SET username = ?, last_seen_date = ? WHERE user_id = ?",
                (username, _today(), user_id),
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


def add_alert(user_id: int, coin: str, price: float, direction: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO alerts (user_id, coin, price, direction) VALUES (?, ?, ?, ?)",
            (user_id, coin, price, direction),
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


# ─── Статистика для админки ───
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
        return {
            "total": total,
            "active_today": active_today,
            "premium": premium,
            "with_alerts": with_alerts,
            "total_alerts": total_alerts,
            "ru_users": ru_users,
            "en_users": en_users,
        }


def all_user_ids() -> list[int]:
    with get_conn() as conn:
        return [r["user_id"] for r in conn.execute("SELECT user_id FROM users").fetchall()]
