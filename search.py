import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote_plus

import requests

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("flight-search")

SERPAPI_KEY = os.getenv("SERPAPI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
SERPAPI_URL = "https://serpapi.com/search.json"
CURRENCY = "EUR"
TRAVEL_CLASS = "2"  # SerpApi: 2 = Premium economy
CABIN_LABEL = "Premium Economy"
ADULTS = 2
MAX_STOPS = "2"  # SerpApi: 2 = nonstop or at most one connection


def telegram_send(text):
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": int(CHAT_ID), "text": text, "disable_web_page_preview": True},
        timeout=25,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendMessage failed: {data}")
    time.sleep(1.0)


def search_oneway(origin, destination, departure_date):
    params = {
        "engine": "google_flights",
        "api_key": SERPAPI_KEY,
        "type": "2",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": departure_date.isoformat(),
        "travel_class": TRAVEL_CLASS,
        "adults": ADULTS,
        "stops": MAX_STOPS,
        "currency": CURRENCY,
        "gl": "at",
        "hl": "en",
        "show_hidden": "true",
    }
    last_error = None
    for attempt in range(4):
        try:
            response = requests.get(SERPAPI_URL, params=params, timeout=60)
            if response.status_code == 429:
                raise RuntimeError("SerpApi rate/quota limit reached (HTTP 429)")
            if response.status_code >= 500:
                time.sleep(min(2 ** attempt, 12))
                continue
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise RuntimeError(payload["error"])
            offers = []
            seen = set()
            for group in ("best_flights", "other_flights"):
                for itinerary in payload.get(group) or []:
                    key = itinerary_key(itinerary)
                    if key and key not in seen:
                        seen.add(key)
                        if valid_itinerary(itinerary):
                            offers.append(itinerary)
            return offers
        except Exception as exc:
            # Never log the request URL: it contains the private SerpApi key.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            last_error = f"{type(exc).__name__} (HTTP {status})" if status else type(exc).__name__
            if status == 429 or "quota limit" in str(exc).lower():
                break
            time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(
        f"SerpApi search failed for {origin}-{destination} {departure_date}: {last_error}"
    )


def itinerary_key(itinerary):
    flights = itinerary.get("flights") or []
    return "|".join(
        f"{f.get('flight_number','')}:{(f.get('departure_airport') or {}).get('time','')}"
        for f in flights
    )


def valid_itinerary(itinerary):
    flights = itinerary.get("flights") or []
    if not flights or len(flights) > 2:
        return False
    # Fail closed: never report Economy or an unknown cabin as Premium Economy.
    return all(
        (flight.get("travel_class") or "").strip().lower() == "premium economy"
        for flight in flights
    )


def itinerary_price(itinerary):
    try:
        return Decimal(str(itinerary["price"]))
    except (KeyError, InvalidOperation, TypeError):
        return None


def itinerary_airports(itinerary):
    flights = itinerary.get("flights") or []
    first = flights[0] if flights else {}
    last = flights[-1] if flights else {}
    origin = (first.get("departure_airport") or {}).get("id", "?")
    destination = (last.get("arrival_airport") or {}).get("id", "?")
    return origin, destination


def segment_lines(itinerary):
    lines = []
    for flight in itinerary.get("flights") or []:
        dep = flight.get("departure_airport") or {}
        arr = flight.get("arrival_airport") or {}
        lines.append(
            f"  • {flight.get('airline','Airline unknown')} "
            f"{flight.get('flight_number','')}: {dep.get('id','?')} → {arr.get('id','?')}\n"
            f"    {dep.get('time','?')} — {arr.get('time','?')} | "
            f"{flight.get('travel_class','cabin unknown')}"
        )
    for layover in itinerary.get("layovers") or []:
        lines.append(
            f"    Пересадка: {layover.get('name', layover.get('id','?'))}; "
            f"{layover.get('duration','?')} мин."
        )
    return lines


def duration_text(itinerary):
    minutes = itinerary.get("total_duration")
    if not isinstance(minutes, (int, float)):
        return "не указана"
    hours, mins = divmod(int(minutes), 60)
    return f"{hours} ч {mins} мин"


def google_flights_link(out_date, return_date):
    query = (
        f"Flights from Vienna to Okinawa on {out_date}; "
        f"return flights from Tokyo to Vienna on {return_date}; "
        f"Premium economy, 2 adults"
    )
    return "https://www.google.com/travel/flights?q=" + quote_plus(query)


def format_pair(outbound, inbound, out_date, return_date):
    out_price = itinerary_price(outbound)
    back_price = itinerary_price(inbound)
    if out_price is None or back_price is None:
        return None
    back_origin, _ = itinerary_airports(inbound)
    total = out_price + back_price
    lines = [
        "🇯🇵 НАЙДЕН ВАРИАНТ — Very Khitry Nihon",
        f"Цена на 2 взрослых: {total:.2f} {CURRENCY}",
        f"Даты: {out_date} → {return_date} (34 ночи)",
        f"Класс: {CABIN_LABEL} туда и обратно",
        f"Маршрут: VIE → OKA / {back_origin} → VIE",
        "",
        "ТУДА:",
        *segment_lines(outbound),
        f"Длительность: {duration_text(outbound)}",
        "Багаж: Google Flights API не вернул надёжные данные о норме багажа",
        "",
        "ОБРАТНО:",
        *segment_lines(inbound),
        f"Длительность: {duration_text(inbound)}",
        "Багаж: Google Flights API не вернул надёжные данные о норме багажа",
        "",
        "Это сочетание двух отдельных поисков в одну сторону; билеты могут оформляться отдельно.",
        "Проверить маршрут и актуальную цену:",
        google_flights_link(out_date, return_date),
    ]
    return "\n".join(lines)[:3900]


def verify_free_quota():
    # Account API calls are free and do not consume the monthly search quota.
    response = requests.get(
        "https://serpapi.com/account.json",
        params={"api_key": SERPAPI_KEY},
        timeout=25,
    )
    response.raise_for_status()
    account = response.json()
    try:
        monthly_price = Decimal(str(account["plan_monthly_price"]))
        searches_left = int(account["plan_searches_left"])
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise RuntimeError("Could not verify SerpApi plan and remaining quota; refusing to search") from exc
    if monthly_price != 0:
        raise RuntimeError(
            f"SerpApi account is not on the free plan (monthly price: {monthly_price}); "
            "refusing to make flight searches"
        )
    if searches_left < 20:
        raise RuntimeError(
            f"Only {searches_left} free SerpApi searches remain; 20 are needed for a full sweep"
        )
    log.info("SerpApi free plan verified; %d searches remain", searches_left)


def main():
    today = datetime.now(timezone.utc).date()
    monitor_start = date(2026, 11, 22)
    monitor_end = date(2026, 12, 1)
    if not monitor_start <= today <= monitor_end:
        log.info("Monitoring window is %s through %s UTC; today is %s. No searches performed.",
                 monitor_start, monitor_end, today)
        return

    missing = [
        name for name, value in (
            ("SERPAPI_API_KEY", SERPAPI_KEY),
            ("TELEGRAM_BOT_TOKEN", TELEGRAM_TOKEN),
            ("TELEGRAM_CHAT_ID", CHAT_ID),
        ) if not value
    ]
    if missing:
        raise RuntimeError("Missing GitHub Actions secrets: " + ", ".join(missing))

    # Refuse to run if the SerpApi account is not free or has insufficient quota.
    verify_free_quota()

    # Exactly ten outbound dates: 12–21 October 2027 inclusive.
    sent = 0
    request_count = 0
    for day_offset in range(10):
        outbound_date = date(2027, 10, 12) + timedelta(days=day_offset)
        return_date = outbound_date + timedelta(days=34)

        # Two searches per date: one outbound, one return. HND and NRT are
        # combined in one departure_id parameter for the return search.
        outbound_offers = search_oneway("VIE", "OKA", outbound_date)
        request_count += 1
        time.sleep(1.2)
        return_offers = search_oneway("HND,NRT", "VIE", return_date)
        request_count += 1
        log.info(
            "%s: %d outbound and %d return Premium Economy options",
            outbound_date, len(outbound_offers), len(return_offers)
        )

        for outbound in outbound_offers:
            for inbound in return_offers:
                message = format_pair(
                    outbound, inbound, outbound_date.isoformat(), return_date.isoformat()
                )
                if message:
                    try:
                        telegram_send(message)
                        sent += 1
                    except Exception:
                        log.exception("Failed to send Telegram alert")

    log.info("Finished: %d SerpApi searches, %d Telegram messages", request_count, sent)


if __name__ == "__main__":
    main()
