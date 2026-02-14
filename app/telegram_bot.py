import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app import calendar_service, nlp_service

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    if calendar_service.is_authenticated(chat_id):
        await update.message.reply_text(
            "이미 인증되었습니다!\n"
            "자연어로 일정을 추가하거나 /today 로 오늘 일정을 확인하세요."
        )
        return

    auth_url = calendar_service.get_auth_url()
    await update.message.reply_text(
        "안녕하세요! 📅 캘린더 봇입니다.\n\n"
        "Google 계정을 연동하려면 아래 링크를 열어 인증해주세요:\n\n"
        f"{auth_url}\n\n"
        "인증 후 브라우저 주소창에서 code= 뒤의 값을 복사하여\n"
        "/auth <코드> 형식으로 보내주세요.\n\n"
        "예: /auth 4/0AX4XfWh..."
    )


async def auth_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text(
            "사용법: /auth <인증코드>\n"
            "인증코드는 Google 인증 후 주소창에서 code= 뒤의 값입니다."
        )
        return

    auth_code = context.args[0]
    await update.message.reply_text("🔄 인증 처리 중...")

    success, message = await calendar_service.authenticate_user(chat_id, auth_code)

    if success:
        await update.message.reply_text(
            f"✅ 인증 성공!\n{message}\n\n"
            "이제 자연어로 일정을 추가할 수 있습니다.\n"
            '예: "내일 오후 3시에 팀 회의"'
        )
    else:
        await update.message.reply_text(f"❌ 인증 실패\n{message}")


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    if not calendar_service.is_authenticated(chat_id):
        await update.message.reply_text("먼저 /start 로 인증을 완료해주세요.")
        return

    try:
        events = await calendar_service.get_today_events()
        text = format_today_events(events)
        await update.message.reply_text(text)
    except Exception:
        logger.exception("Error fetching today's events")
        await update.message.reply_text("일정을 불러오는 중 오류가 발생했습니다.")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_message = update.message.text

    if not calendar_service.is_authenticated(chat_id):
        await update.message.reply_text("먼저 /start 로 인증을 완료해주세요.")
        return

    parsed = await nlp_service.parse_event(user_message)

    if parsed is None:
        await update.message.reply_text(
            "일정 정보를 인식하지 못했습니다. 다시 시도해주세요.\n"
            '예: "내일 오후 2시에 치과 예약"'
        )
        return

    success, result = await calendar_service.add_event(
        chat_id=chat_id,
        title=parsed["title"],
        date=parsed["date"],
        start_time=parsed["start_time"],
        end_time=parsed.get("end_time"),
        description=parsed.get("description"),
    )

    if success:
        time_str = parsed["start_time"]
        if parsed.get("end_time"):
            time_str += f" - {parsed['end_time']}"

        reply = (
            "✅ 일정이 추가되었습니다!\n\n"
            f"📅 {parsed['date']}\n"
            f"🕐 {time_str}\n"
            f"📝 {parsed['title']}"
        )
        if parsed.get("description"):
            reply += f"\n💬 {parsed['description']}"

        await update.message.reply_text(reply)
    else:
        await update.message.reply_text(f"❌ 일정 추가 실패\n{result}")


def format_today_events(events: list[dict]) -> str:
    if not events:
        return "📭 오늘은 예정된 일정이 없습니다."

    lines = ["📅 오늘의 일정:\n"]
    for i, event in enumerate(events, 1):
        summary = event.get("summary", "(제목 없음)")
        start = event.get("start", {})
        if "dateTime" in start:
            time_str = start["dateTime"][11:16]
        else:
            time_str = "종일"
        lines.append(f"{i}. 🕐 {time_str} - {summary}")

    return "\n".join(lines)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update:", exc_info=context.error)

    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            )
        except Exception:
            pass


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("auth", auth_command))
    application.add_handler(CommandHandler("today", today_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
    application.add_error_handler(error_handler)
