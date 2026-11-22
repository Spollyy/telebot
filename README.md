# Very Khitry Nihon Flight Watch

Personal Telegram flight watcher. Uses SerpApi's Google Flights engine; no Duffel, paid server, or database.

## Flight search rules

- 2 adults
- Premium Economy only on every segment, outbound and return
- Outbound: Vienna (VIE) to Okinawa (OKA), 12–21 October 2027 inclusive (10 dates)
- Return: Tokyo Haneda (HND) or Narita (NRT) to Vienna (VIE), exactly 34 nights after departure
- At most 1 connection per direction
- All airlines

## Monitoring window

- Start: 22 November 2026 UTC
- End: 1 December 2026 UTC (10 calendar days inclusive)
- One sweep per UTC day
- Scheduled time: 08:00 UTC
- The script refuses to search outside this window.
- GitHub Actions cache prevents a second quota-consuming run on the same UTC day after a successful sweep.

The first sweep for today must be started manually from **Actions → Very Khitry Nihon Flight Watch → Run workflow**. The daily schedule will run at 08:00 UTC on the following days.

## Search volume and free quota

Each sweep makes up to 20 SerpApi searches:
- 10 outbound searches (VIE → OKA)
- 10 return searches (HND and NRT combined in one query per date)

Ten daily sweeps use up to 200 searches. SerpApi's free plan advertises 250 searches per month. Before every sweep, the script calls the free Account API and refuses to search unless the monthly plan price is $0 and at least 20 searches remain. The Account API itself does not consume search quota. If the free quota has been partly used already, the script may stop before searching.

## GitHub Actions setup

In this public repository, open **Settings → Secrets and variables → Actions → New repository secret**.
Required secrets:

- `SERPAPI_API_KEY`: SerpApi API key
- `TELEGRAM_BOT_TOKEN`: a newly generated Telegram bot token from @BotFather
- `TELEGRAM_CHAT_ID`: numeric Telegram chat ID

Never paste credentials into chat or commit them to this public repository.

## Result limitations

The script only accepts results where every segment is explicitly labelled Premium economy and there are no more than two flight segments. If the API does not explicitly identify the cabin, that itinerary is discarded rather than guessed. Baggage allowance may not be included in search results, so the bot will say it is not confirmed.

Outbound and return are searched independently and paired by date. They may be separate tickets and booking references. Telegram messages include the Google Flights search link, not a guaranteed direct booking URL.

## Infrastructure

- GitHub Actions: scheduled runner
- SerpApi: flight-search data
- Telegram Bot API: message delivery
- No Render, database, Duffel, or always-on server
