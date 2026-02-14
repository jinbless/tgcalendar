import logging

from telegram.ext import ApplicationBuilder, Defaults

from app.config import TELEGRAM_BOT_TOKEN, TIMEZONE
from app.scheduler import schedule_daily_report
from app.telegram_bot import register_handlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def post_init(application) -> None:
    schedule_daily_report(application)
    logger.info("Post-init complete: scheduler configured")


def main() -> None:
    defaults = Defaults(tzinfo=TIMEZONE)

    application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .defaults(defaults)
        .post_init(post_init)
        .build()
    )

    register_handlers(application)

    logger.info("Starting bot...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
