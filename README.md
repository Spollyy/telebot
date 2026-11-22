# Very Khitry Nihon Flight Watch

A personal Telegram flight watcher running on GitHub Actions (no paid server or database).

## Search rules

- 2 adults
- Outbound: Vienna (VIE) to Okinawa (OKA), 1–22 October 2027 inclusive
- Return: Tokyo (HND or NRT) to Vienna (VIE), exactly 34 nights after outbound
- At most 1 connection on each direction
- Four cabin combinations: Economy/Economy, Economy/Premium Economy,
  Premium Economy/Economy, Premium Economy/Premium Economy
- Scheduled every 6 hours (UTC); can also be started manually
- Sends all matching combinations without a price threshold

## GitHub Actions setup

In this public repository, open **Settings → Secrets and variables → Actions → New repository secret**.
Add these three secrets:

- `TELEGRAM_BOT_TOKEN`: a newly generated token from @BotFather (revoke the token previously pasted into chat)
- `TELEGRAM_CHAT_ID`: your numeric Telegram chat ID (for example, message @userinfobot)
- `DUFFEL_ACCESS_TOKEN`: a Duffel **live** access token, not a test token

Then open **Actions → Very Khitry Nihon Flight Watch → Run workflow** to test it.
Scheduled runs happen every six hours. GitHub-hosted standard runners are free for public repositories.

## Important API cost note

GitHub Actions hosting is free for this public repository. Live flight-search data is a separate matter:
Duffel's pricing currently includes a 1,500:1 search-to-book ratio and charges $0.005 per excess search.
This watcher currently performs up to 132 one-way offer searches per sweep (22 dates, two cabins,
and Tokyo's two airports), or about 15,840 searches in a 30-day month if every run completes.
If there are no bookings against the account, the searches may become chargeable. Review Duffel's
current pricing before enabling scheduled live searches. A Duffel test token returns sandbox data,
not realistic live fares.

## Security

Never commit real credentials or paste them into chat. GitHub Actions secrets are used at runtime.
The repository is public, so only code and documentation belong here.

## Architecture

- GitHub Actions: scheduled runner
- Duffel: flight offers (live API access required for real fares)
- Telegram Bot API: delivery
- No Render service, database, or always-on server
