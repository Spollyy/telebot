import logging
import os

import requests
from flask import Flask, jsonify, request
import psycopg
from psycopg.rows import dict_row

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("nihon-bot")

app = Flask(__name__)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DB_URL = os.getenv("DATABASE_URL", "").strip()
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()


def db():
    if not DB_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DB_URL, row_factory=dict_row)


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telegram_subscribers (
                chat_id BIGINT PRIMARY KEY,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                is_active BOOLEAN NOT NULL DEFAULT TRUE
            )
        """)


def telegram(method, payload):
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        json=payload,
        timeout=25,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API {method} failed: {data}")
    return data.get("result")


def set_webhook():
    external_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not external_url or not BOT_TOKEN or not WEBHOOK_SECRET:
        log.warning("Webhook not registered: set RENDER_EXTERNAL_URL, bot token and webhook secret")
        return
    try:
        telegram("setWebhook", {
            "url": f"{external_url}/telegram/webhook",
            "secret_token": WEBHOOK_SECRET,
            "allowed_updates": ["message"],
            "drop_pending_updates": False,
        })
        log.info("Telegram webhook registered")
    except Exception:
        log.exception("Could not register Telegram webhook")


@app.get("/")
def health():
    return jsonify({"ok": True, "service": "Very Khitry Nihon Flight Watch"})


@app.post("/telegram/webhook")
def webhook():
    if WEBHOOK_SECRET:
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if supplied != WEBHOOK_SECRET:
            return jsonify({"ok": False}), 403

    update = request.get_json(silent=True) or {}
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()

    if not chat_id:
        return jsonify({"ok": True})

    if text.startswith("/start") or text.startswith("/subscribe"):
        try:
            with db() as conn:
                conn.execute(
                    """INSERT INTO telegram_subscribers (chat_id, is_active)
                       VALUES (%s, TRUE)
                       ON CONFLICT (chat_id) DO UPDATE SET is_active = TRUE""",
                    (chat_id,),
                )
            telegram("sendMessage", {
                "chat_id": chat_id,
                "text": (
                    "🇯🇵 Very Khitry Nihon Flight Watch подключён!\n\n"
                    "Буду присылать найденные варианты VIE → OKA и Tokyo → VIE "
                    "для поездки ровно на 34 ночи. Проверки планируются каждые 6 часов.\n\n"
                    "Команды: /status — настройки, /stop — отключить уведомления."
                ),
            })
        except Exception:
            log.exception("Failed to subscribe chat %s", chat_id)
            return jsonify({"ok": False}), 500

    elif text.startswith("/stop"):
        with db() as conn:
            conn.execute(
                "UPDATE telegram_subscribers SET is_active = FALSE WHERE chat_id = %s",
                (chat_id,),
            )
        telegram("sendMessage", {
            "chat_id": chat_id,
            "text": "Уведомления отключены. Чтобы включить снова, отправь /start.",
        })

    elif text.startswith("/status"):
        telegram("sendMessage", {
            "chat_id": chat_id,
            "text": (
                "Маршрут: VIE → OKA / HND или NRT → VIE\n"
                "Даты вылета: 1–22 октября 2027\n"
                "Продолжительность: ровно 34 ночи\n"
                "Пассажиры: 2 взрослых\n"
                "Классы: Economy и Premium Economy в обе стороны\n"
                "Пересадки: максимум 1 на каждое направление\n"
                "Расписание: каждые 6 часов (UTC)"
            ),
        })

    else:
        telegram("sendMessage", {
            "chat_id": chat_id,
            "text": "Доступные команды: /start, /status, /stop",
        })

    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    set_webhook()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
