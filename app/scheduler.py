import logging
from datetime import time

import telegram.error
from telegram.ext import Application, ContextTypes

from app import calendar_service
from app.config import DAILY_REPORT_TIME, TIMEZONE
from app.telegram_bot import format_today_events

logger = logging.getLogger(__name__)


async def daily_report_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Running daily report job")

    try:
        events = await calendar_service.get_today_events()
    except Exception:
        logger.exception("Failed to fetch today's events for daily report")
        return

    text = format_today_events(events)
    chat_ids = calendar_service.get_all_authenticated_chat_ids()

    if not chat_ids:
        logger.info("No authenticated users to send daily report to")
        return

    for chat_id in chat_ids:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except telegram.error.Forbidden:
            logger.warning("User %s blocked the bot", chat_id)
        except Exception:
            logger.exception("Failed to send daily report to chat_id=%s", chat_id)


def schedule_daily_report(application: Application) -> None:
    hour, minute = map(int, DAILY_REPORT_TIME.split(":"))
    report_time = time(hour=hour, minute=minute, tzinfo=TIMEZONE)

    application.job_queue.run_daily(
        callback=daily_report_job,
        time=report_time,
        name="daily_report",
    )
    logger.info("Scheduled daily report at %s %s", DAILY_REPORT_TIME, TIMEZONE)
