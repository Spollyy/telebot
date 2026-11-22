# Very Khitry Nihon Flight Watch

Personal Telegram flight-alert project. Flight searches are currently **paused**.

## Intended search rules

- 2 adults
- Outbound: Vienna (VIE) to Okinawa (OKA), 1–22 October 2027 inclusive
- Return: Tokyo (HND or NRT) to Vienna (VIE), exactly 34 nights after outbound
- At most 1 connection per direction
- Four cabin combinations: Economy/Economy, Economy/Premium Economy,
  Premium Economy/Economy, Premium Economy/Premium Economy
- Intended monitoring cadence: every 6 hours for up to 21 days
- Send matching results to one Telegram chat

## Why searches are paused

There is no official free Google Flights API. Google's published machine-readable access rules disallow automated crawling of its flight-search pages. This project will not bypass those restrictions or use paid flight-search APIs without explicit approval.

The previous Duffel-based search script is retained as legacy code only and is not invoked by the workflow. The GitHub Actions workflow is currently a harmless manual status check; it does not search flights or send Telegram messages.

## Infrastructure

- GitHub Actions: no always-on server
- No database
- Telegram Bot API: intended alert delivery
- No paid flight-data provider currently configured

## Security

Never commit credentials or paste them into chat. Store any required Telegram credentials only as GitHub Actions repository secrets.
