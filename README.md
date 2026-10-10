# WILD WHITE BULLFFALLO

Telegram anti-raid and Solana buy-alert bot for mint `5T7V8epXn2LeoyxqzkWa1pPStJGGQ2i3cQiUQvw8pump`.

## Features
- Join verification: button + randomized arithmetic challenge.
- Pending members are muted; expired or repeatedly failed verification is removed.
- Raid heuristic: alert/temporary raid mode after a configurable join burst.
- Flood and unapproved-link filters.
- Admin commands: `/status`, `/lockdown`, `/unlock`, `/verifycheck`.
- Helius Enhanced Transactions polling for swap-classified transactions transferring the configured mint.

## Setup
1. Create a bot with [@BotFather](https://t.me/BotFather).
2. Add it to the Telegram supergroup as an administrator. Grant permission to restrict members, delete messages, ban members, and manage join requests.
3. Copy `.env.example` to `.env`. Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_GROUP_ID`, `ADMIN_USER_IDS`, and `HELIUS_API_KEY`.
4. Get a Helius API key at [helius.dev](https://www.helius.dev/).
5. Install Python 3.12+ and run:
   ```sh
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   python bot.py
   ```
   Or deploy the included Dockerfile to a persistent container host such as Railway.

Never commit your real `.env`, Telegram bot token, or Helius API key.

## Telegram notes
- The bot needs admin permissions to apply moderation. Configure BotFather privacy settings if it must inspect ordinary group messages.
- Join-request handling in this starter approves the request and then restricts the member. This is not a strictly pre-join gate; private deep-link verification before approval would be needed for that.
- Link filtering is strict by default; set `ALLOW_MEMBER_LINKS=true` to allow links from regular members.

## Buy-alert limitations
Alerts rely on Helius Enhanced Transactions classifying a transaction as `SWAP` and showing a positive transfer of the configured mint. Coverage can vary for Pump.fun bonding-curve trades, aggregators, and migrated DEX routes. Test against real buys before relying on it for every transaction. This starter polls every 5 seconds and stores deduplication state in memory, so restarts may cause duplicate alerts. For production, use Helius webhooks and persistent signature storage, and test Pump.fun/Raydium coverage. USD valuation and minimum-buy thresholds are not implemented; alerts should not be treated as complete until tested.
