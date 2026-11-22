import concurrent.futures
import logging
import os
import time
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote_plus

import psycopg
import requests
from psycopg.rows import dict_row

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("flight-search")

DUFFEL_TOKEN = os.getenv("DUFFEL_ACCESS_TOKEN", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DB_URL = os.getenv("DATABASE_URL", "").strip()
DUFFEL_URL = "https://api.duffel.com/air/offer_requests"
CABINS = ("economy", "premium_economy")
CABIN_LABEL = {"economy": "Economy", "premium_economy": "Premium Economy"}
MAX_WORKERS = int(os.getenv("SEARCH_CONCURRENCY", "4"))


def db():
    if not DB_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DB_URL, row_factory=dict_row)


def active_chats():
    with db() as conn:
        rows = conn.execute(
            "SELECT chat_id FROM telegram_subscribers WHERE is_active = TRUE"
        ).fetchall()
    return [row["chat_id"] for row in rows]


def telegram_send(chat_id, text):
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=25,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendMessage failed: {data}")
    time.sleep(0.9)  # stay below Telegram's per-chat message rate


def search_one(origin, destination, departure_date, cabin):
    headers = {
        "Authorization": f"Bearer {DUFFEL_TOKEN}",
        "Duffel-Version": "v2",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "data": {
            "slices": [{
                "origin": origin,
                "destination": destination,
                "departure_date": departure_date.isoformat(),
            }],
            "passengers": [{"type": "adult"}, {"type": "adult"}],
            "cabin_class": cabin,
            "max_connections": 1,
        }
    }
    last_error = None
    for attempt in range(4):
        try:
            response = requests.post(
                DUFFEL_URL,
                params={"return_offers": "true", "supplier_timeout": "10000"},
                headers=headers,
                json=payload,
                timeout=35,
            )
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(min(2 ** attempt, 12))
                continue
            response.raise_for_status()
            data = response.json().get("data", {})
            return {
                "origin": origin,
                "destination": destination,
                "date": departure_date.isoformat(),
                "cabin": cabin,
                "offers": data.get("offers") or [],
            }
        except Exception as exc:
            last_error = exc
            time.sleep(min(2 ** attempt, 12))
    log.warning("Duffel search failed %s-%s %s %s: %s",
                origin, destination, departure_date, cabin, last_error)
    return {
        "origin": origin, "destination": destination,
        "date": departure_date.isoformat(), "cabin": cabin, "offers": [],
    }


def actual_segment_cabins(offer):
    found = []
    for slice_data in offer.get("slices") or []:
        for segment in slice_data.get("segments") or []:
            passenger_rows = segment.get("passengers") or []
            cabin = None
            if passenger_rows:
                cabin = passenger_rows[0].get("cabin_class")
            if not cabin:
                # Duffel's offer-level passenger cabin is a safe fallback only
                # when the segment itself does not expose a passenger cabin.
                cabin = None
            found.append(cabin)
    return found


def offer_matches_cabin(offer, requested_cabin):
    cabins = actual_segment_cabins(offer)
    # Never silently label an itinerary Premium Economy if segment-level
    # cabin data is absent or a segment is sold in another cabin.
    return bool(cabins) and all(c == requested_cabin for c in cabins)


def amount(offer):
    try:
        return Decimal(str(offer["total_amount"])), offer["total_currency"]
    except (KeyError, InvalidOperation):
        return None, None


def airport(place):
    if not isinstance(place, dict):
        return "?"
    return place.get("iata_code") or place.get("name") or "?"


def segment_lines(offer):
    lines = []
    for slice_data in offer.get("slices") or []:
        for segment in slice_data.get("segments") or []:
            op = segment.get("operating_carrier") or {}
            marketing = segment.get("marketing_carrier") or {}
            carrier = op.get("name") or marketing.get("name") or "Авиакомпания не указана"
            flight_no = segment.get("marketing_carrier_flight_number") or ""
            origin = airport(segment.get("origin"))
            dest = airport(segment.get("destination"))
            dep = (segment.get("departing_at") or "?").replace("T", " ")
            arr = (segment.get("arriving_at") or "?").replace("T", " ")
            pax = (segment.get("passengers") or [{}])[0]
            cabin = pax.get("cabin_class")
            cabin_name = pax.get("cabin_class_marketing_name") or CABIN_LABEL.get(cabin, "класс не указан")
            lines.append(
                f"  • {carrier} {flight_no}: {origin} → {dest}\n"
                f"    {dep} — {arr}; салон: {cabin_name}"
            )
    return lines


def baggage_summary(offer):
    bits = []
    for slice_data in offer.get("slices") or []:
        for segment in slice_data.get("segments") or []:
            pax_rows = segment.get("passengers") or []
            for bag in (pax_rows[0].get("baggages") or []) if pax_rows else []:
                quantity = bag.get("quantity")
                typ = bag.get("type") or "багаж"
                if quantity is not None:
                    bits.append(f"{typ}: {quantity}")
    return ", ".join(dict.fromkeys(bits)) if bits else "не указано в ответе API"


def duration(offer):
    values = []
    for sl in offer.get("slices") or []:
        if sl.get("duration"):
            values.append(sl["duration"])
    return " / ".join(values) if values else "не указана"


def offer_key(offer):
    parts = []
    for sl in offer.get("slices") or []:
        for seg in sl.get("segments") or []:
            carrier = (seg.get("operating_carrier") or {}).get("iata_code", "")
            number = seg.get("marketing_carrier_flight_number", "")
            parts.append(f"{carrier}{number}:{seg.get('departing_at','')}")
    return "|".join(parts)


def google_flights_link(out_date, return_date, return_airport):
    query = (
        f"Flights from Vienna to Okinawa on {out_date}; "
        f"return flights from {return_airport} to Vienna on {return_date}"
    )
    return "https://www.google.com/travel/flights?q=" + quote_plus(query)


def format_pair(out_offer, back_offer, out_date, return_date, out_cabin, back_cabin, back_airport):
    out_amount, out_currency = amount(out_offer)
    back_amount, back_currency = amount(back_offer)
    if out_amount is None or back_amount is None or out_currency != back_currency:
        return None
    total = out_amount + back_amount
    lines = [
        "🇯🇵 НАЙДЕН ВАРИАНТ — Very Khitry Nihon",
        f"Цена на 2 взрослых: {total:.2f} {out_currency}",
        f"Даты: {out_date} → {return_date} (34 ночи)",
        f"Классы: туда {CABIN_LABEL[out_cabin]} / обратно {CABIN_LABEL[back_cabin]}",
        f"Маршрут: VIE → OKA / {back_airport} → VIE",
        "",
        "ТУДА:",
        *segment_lines(out_offer),
        f"Длительность: {duration(out_offer)}",
        f"Багаж: {baggage_summary(out_offer)}",
        "",
        "ОБРАТНО:",
        *segment_lines(back_offer),
        f"Длительность: {duration(back_offer)}",
        f"Багаж: {baggage_summary(back_offer)}",
        "",
        f"ID предложения туда: {out_offer.get('id','нет')}",
        f"ID предложения обратно: {back_offer.get('id','нет')}",
        "Бронирование: это два независимых one-way предложения; могут быть отдельные билеты и PNR.",
        "Ссылка для дополнительной проверки маршрута (не прямая ссылка на эти тарифы):",
        google_flights_link(out_date, return_date, back_airport),
    ]
    text = "\n".join(lines)
    return text[:3900]


def main():
    if not DUFFEL_TOKEN or not TELEGRAM_TOKEN or not DB_URL:
        raise RuntimeError("Set DUFFEL_ACCESS_TOKEN, TELEGRAM_BOT_TOKEN and DATABASE_URL")
    chats = active_chats()
    if not chats:
        log.info("No Telegram subscribers yet; open the bot and send /start")
        return

    jobs = []
    start = date(2027, 10, 1)
    end = date(2027, 10, 22)
    day = start
    while day <= end:
        back = day + timedelta(days=34)
        for cabin in CABINS:
            jobs.append(("VIE", "OKA", day, cabin))
            for tokyo in ("HND", "NRT"):
                jobs.append((tokyo, "VIE", back, cabin))
        day += timedelta(days=1)

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_map = {
            pool.submit(search_one, origin, destination, dep_date, cabin):
                (origin, destination, dep_date.isoformat(), cabin)
            for origin, destination, dep_date, cabin in jobs
        }
        for future in concurrent.futures.as_completed(future_map):
            key = future_map[future]
            try:
                results[key] = future.result()
            except Exception:
                log.exception("Search task failed: %s", key)
                results[key] = {"offers": []}

    sent = 0
    for out_date_num in range(1, 23):
        out_date = date(2027, 10, out_date_num)
        return_date = out_date + timedelta(days=34)
        out_offers = {}
        back_offers = {}
        for cabin in CABINS:
            res = results.get(("VIE", "OKA", out_date.isoformat(), cabin), {})
            out_offers[cabin] = [
                o for o in res.get("offers", []) if offer_matches_cabin(o, cabin)
            ]
            for tokyo in ("HND", "NRT"):
                res = results.get((tokyo, "VIE", return_date.isoformat(), cabin), {})
                back_offers[(tokyo, cabin)] = [
                    o for o in res.get("offers", []) if offer_matches_cabin(o, cabin)
                ]

        for out_cabin in CABINS:
            for back_cabin in CABINS:
                for tokyo in ("HND", "NRT"):
                    for outbound in out_offers[out_cabin]:
                        for inbound in back_offers[(tokyo, back_cabin)]:
                            msg = format_pair(
                                outbound, inbound, out_date.isoformat(),
                                return_date.isoformat(), out_cabin, back_cabin, tokyo
                            )
                            if not msg:
                                continue
                            for chat_id in chats:
                                try:
                                    telegram_send(chat_id, msg)
                                    sent += 1
                                except Exception:
                                    log.exception("Telegram send failed for chat %s", chat_id)
    log.info("Search sweep finished. Queries=%s, messages_sent=%s", len(jobs), sent)


if __name__ == "__main__":
    main()
