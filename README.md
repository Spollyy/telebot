# Very Khitry Nihon Flight Watch

Telegram flight-alert bot for a 34-night Japan trip in October/November 2027.

## Search rules

- 2 adults
- Outbound: Vienna (VIE) to Okinawa (OKA), 1–22 October 2027 inclusive
- Return: Tokyo (HND or NRT) to Vienna (VIE), exactly 34 nights after outbound
- At most 1 connection per direction
- All carriers supported by the selected flight API
- Four cabin combinations: Economy/Economy, Economy/Premium Economy,
  Premium Economy/Economy, Premium Economy/Premium Economy
- Intended search cadence: every 6 hours
- Send every qualifying itinerary; no price threshold

## Secrets

Set `TELEGRAM_BOT_TOKEN`, `DUFFEL_ACCESS_TOKEN`, `DATABASE_URL`, and
`TELEGRAM_WEBHOOK_SECRET` as private Render environment variables.
Never commit real credentials or paste them into chat.

The Telegram token previously shared in chat must be revoked in @BotFather.
Use only a newly generated token.

## Current status

This is the initial deployment scaffold. Flight search, Telegram delivery,
persistence, and scheduled Render jobs must be implemented/configured before
the bot is live.
