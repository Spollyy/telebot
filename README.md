# Very Khitry Nihon Flight Watch

Personal Telegram flight watcher. The search code uses SerpApi's Google Flights engine and does not use Duffel.

## Search rules

- 2 adults
- Premium Economy only, outbound and return
- Outbound: Vienna (VIE) to Okinawa (OKA), 12–21 October 2027 inclusive (exactly 10 dates)
- Return: Tokyo (HND or NRT) to Vienna (VIE), exactly 34 nights after outbound
- At most 1 connection per direction
- All airlines
- Results sent to one Telegram chat

## Search volume and free quota

Each daily full sweep makes 20 SerpApi searches:
- 10 outbound searches (VIE → OKA)
- 10 return searches (HND or NRT → VIE; both Tokyo airports are combined in one query)

For 10 daily sweeps, that is 200 searches. SerpApi currently advertises 250 searches/month on its free plan, leaving an estimated 50-search buffer. Quotas and plan terms can change; check your account dashboard before starting. This project does not intentionally make extra booking-detail requests.

## GitHub Actions setup

In this public repository, open **Settings → Secrets and variables → Actions → New repository secret**.
Add these secrets:

- `SERPAPI_API_KEY`: your SerpApi key
- `TELEGRAM_BOT_TOKEN`: a newly generated Telegram bot token from @BotFather
- `TELEGRAM_CHAT_ID`: your numeric Telegram chat ID

Do not paste secrets into chat or commit them to the public repository.

The workflow is currently **manual-only**. After adding the secrets, run **Actions → Very Khitry Nihon Flight Watch → Run workflow** for a test. Once the monitoring start date is chosen, a daily schedule can be enabled for a 10-day period; disable it after the tenth run. GitHub Actions runs on a public repository do not require a paid always-on server.

## Result limitations

SerpApi returns Google Flights itinerary listings, including flight segments, cabin class, prices, airlines and layovers when provided. The script rejects itineraries unless every segment is explicitly labelled Premium economy and there are no more than two flight segments. Baggage allowance may not be present in the search response, so the bot will not guess it.

Outbound and return are searched independently and paired by date. They may be separate tickets and booking references. The message links to a Google Flights search, not a guaranteed direct booking URL.

## Infrastructure

- GitHub Actions: runner only
- SerpApi: Google Flights results provider
- Telegram Bot API: alerts
- No Render, database, Duffel, or always-on server
