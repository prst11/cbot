import os
import requests

NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY", "")
BASE_URL = "https://api.nowpayments.io/v1"
HEADERS = {"x-api-key": NOWPAYMENTS_API_KEY, "Content-Type": "application/json"}


def create_invoice(amount_usd: float, order_id: str, description: str) -> dict:
    """
    Создаёт инвойс через NOWPayments. Валюта оплаты не зафиксирована (pay_currency не указан) —
    на странице оплаты юзер сам выбирает, какой монетой платить. Логично для крипто-аудитории,
    у которой уже есть монеты на балансе.
    """
    payload = {
        "price_amount": amount_usd,
        "price_currency": "usd",
        "order_id": order_id,
        "order_description": description,
    }
    resp = requests.post(f"{BASE_URL}/invoice", headers=HEADERS, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_payment_status(payment_id: str) -> dict:
    resp = requests.get(f"{BASE_URL}/payment/{payment_id}", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def is_payment_successful(status_data: dict) -> bool:
    return status_data.get("payment_status") in ("finished", "confirmed")
