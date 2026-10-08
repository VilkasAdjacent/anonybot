# anonybot

Allows users to send messages anonymously to a channel.

Built for a specific use case, so not particularly good code, but maybe useful as an example.

## Instructions
- Clone this repo
- Install [uv](https://docs.astral.sh/uv/) and run `uv sync`
- Create a .env file with your bot's token (`BOT_TOKEN=abcd_i_am_a_token`), plus `OPENROUTER_API_KEY` (AI mode) and `REPLICATE_API_TOKEN` (song generation)
- Optionally set `IGNORED_CHANNEL_IDS` to a comma-separated list of channel/thread IDs the bot should never process (no replies, no reactions, nothing sent to an LLM). Listing a channel ID also mutes its threads.
- Run via `uv run anonybot.py`