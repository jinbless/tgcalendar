# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram bot for managing a shared Google Calendar via natural language (Korean). Users send messages in Telegram, OpenAI GPT-4.1 parses intent via function calling, and the bot executes corresponding Google Calendar API operations. Also supports Google Maps navigation/directions.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (requires .env with all required vars)
python -m app.main

# Run with Docker
docker-compose up -d

# Build Docker image
docker build -t tgcalendar:latest .
```

No test framework or linter is configured. Python 3.11+ required (uses `X | Y` union syntax, `ZoneInfo`).

## Architecture

All code lives in `app/`. Single entry point: `python -m app.main`.

### Data flow

1. User sends Telegram message → `telegram_bot.py:handle_text_message`
2. `nlp_service.py:process_message` sends message + history to GPT with function-calling tools
3. GPT returns either a text response or a tool call (e.g. `add_event`, `delete_event`)
4. `telegram_bot.py` dispatches via `FUNCTION_REGISTRY` dict → executor calls `calendar_service.py`
5. For queries: result fed back to GPT via `get_followup_response` for natural language summary
6. For mutations: result shown directly + affected month's event list appended
7. For navigation: geocode via Google Geocoding API → prompt user for location share → build Google Maps directions URL

### Key modules

- **config.py** — All env vars and constants. Single source of truth for paths, API keys, timezone.
- **nlp_service.py** — GPT integration. `TOOLS` list defines 11 function schemas. `SYSTEM_PROMPT` is Korean with `{today}`/`{weekday}` placeholders. Per-user conversation history stored in-memory (`_chat_histories`, max 100 messages FIFO).
- **telegram_bot.py** — Handler registration, function dispatch, event formatting. Three function categories: `_MUTATION_FUNCTIONS`, `_QUERY_FUNCTIONS`, `_NAVIGATION_FUNCTIONS`.
- **calendar_service.py** — Google Calendar CRUD. All sync Google API calls wrapped with `asyncio.to_thread()`. Event matching logic: title match → time match → single-event fallback.
- **geo_service.py** — Google Maps Geocoding API + Google Maps directions URL builder.
- **scheduler.py** — Daily report job via `python-telegram-bot` job queue (not standalone APScheduler). Sends today's events to all authenticated users.
- **web_server.py** — aiohttp server for OAuth callback (`/oauth/callback`). Runs alongside the bot, started in `post_init`.

### Key patterns

- **Async throughout**: All handlers are async. Sync Google API calls wrapped with `asyncio.to_thread()`.
- **Shared calendar**: All users operate on `SHARED_CALENDAR_ID`, not personal calendars. Query functions (`get_today_events`, `get_week_events`) use `_get_any_valid_creds()` — any authenticated user's token works.
- **OAuth via web callback**: `main.py:post_init` starts an aiohttp server. Google OAuth redirects to `/oauth/callback` with `state=chat_id`, which exchanges the code and notifies the user via Telegram.
- **Post-mutation month summary**: After add/edit/delete, `_get_month_summary` fetches and sends that month's full event list.
- **Navigation two-step flow**: `navigate`/`navigate_to_event` geocodes destination via Google and stores in `_pending_navigation`, then `handle_location` builds a Google Maps directions URL.
- **GPT two-pass for queries**: Query results are fed back to GPT (via `get_followup_response`) so it can compose a natural Korean response.
- **search_events skips Google API `q` param**: Fetches all events in range and lets GPT filter semantically (Google's `q` does word-level matching, misses Korean substrings).

## Environment Setup

Copy `.env.example` to `.env`. Required vars: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SHARED_CALENDAR_ID`. Optional: `GOOGLE_MAPS_API_KEY` (for navigation), `GOOGLE_REDIRECT_URI`, `DAILY_REPORT_TIME`, `TIMEZONE`, `OAUTH_SERVER_PORT`.

Token storage: `data/tokens/{chat_id}.json` (volume-mounted in Docker).
