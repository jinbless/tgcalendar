import logging
from datetime import datetime

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

WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


# ── Command Handlers ──────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    if calendar_service.is_authenticated(chat_id):
        await update.message.reply_text(
            "이미 인증되었습니다!\n"
            "자연어로 일정을 관리하세요.\n\n"
            "💡 사용 예시:\n"
            '• "내일 오후 3시에 팀 회의"\n'
            '• "오늘 일정 뭐야?"\n'
            '• "이번 주 일정 알려줘"\n'
            '• "내일 팀 회의 삭제해줘"\n'
            '• "팀 회의 시간 4시로 변경해줘"\n'
            '• "2월 일정 다 지워줘"'
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
            "이제 자연어로 일정을 관리할 수 있습니다.\n"
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
        await update.message.reply_text(format_today_events(events))
    except Exception:
        logger.exception("Error fetching today's events")
        await update.message.reply_text("일정을 불러오는 중 오류가 발생했습니다.")


# ── Function Registry ─────────────────────────────────────────────

async def _exec_add_event(chat_id: int, args: dict) -> str:
    success, result = await calendar_service.add_event(chat_id=chat_id, **args)
    if success:
        time_str = args["start_time"]
        if args.get("end_time"):
            time_str += f" - {args['end_time']}"
        reply = f"✅ 일정이 추가되었습니다!\n\n📅 {args['date']}\n🕐 {time_str}\n📝 {args['title']}"
        if args.get("description"):
            reply += f"\n💬 {args['description']}"
        return reply
    return f"❌ 일정 추가 실패\n{result}"


async def _exec_delete_event(chat_id: int, args: dict) -> str:
    success, result = await calendar_service.delete_event(chat_id=chat_id, **args)
    if success:
        return f"🗑️ 일정이 삭제되었습니다!\n\n📅 {args['date']}\n📝 {result}"
    return f"❌ 일정 삭제 실패\n{result}"


async def _exec_delete_events_by_range(chat_id: int, args: dict) -> str:
    count, error = await calendar_service.delete_events_by_range(chat_id=chat_id, **args)
    if count > 0:
        msg = f"🗑️ {count}개 일정이 삭제되었습니다!\n\n📅 {args['date_from']} ~ {args['date_to']}"
        if args.get("keyword"):
            msg += f'\n🔍 키워드: "{args["keyword"]}"'
        return msg
    return f"❌ 일정 삭제 실패\n{error}"


async def _exec_edit_event(chat_id: int, args: dict) -> str:
    success, result = await calendar_service.edit_event(chat_id=chat_id, **args)
    if success:
        changes = args.get("changes", {})
        reply = f"✏️ 일정이 수정되었습니다!\n\n📝 {result}"
        details = []
        if changes.get("title"):
            details.append(f"제목 → {changes['title']}")
        if changes.get("date"):
            details.append(f"날짜 → {changes['date']}")
        if changes.get("start_time"):
            details.append(f"시작 → {changes['start_time']}")
        if changes.get("end_time"):
            details.append(f"종료 → {changes['end_time']}")
        if changes.get("description"):
            details.append(f"설명 → {changes['description']}")
        if details:
            reply += "\n\n변경사항:\n" + "\n".join(f"• {d}" for d in details)
        return reply
    return f"❌ 일정 수정 실패\n{result}"


async def _exec_get_today_events(chat_id: int, args: dict) -> str:
    events = await calendar_service.get_today_events()
    return format_today_events(events)


async def _exec_get_week_events(chat_id: int, args: dict) -> str:
    events = await calendar_service.get_week_events()
    return format_week_events(events)


async def _exec_search_events(chat_id: int, args: dict) -> str:
    events = await calendar_service.search_events(chat_id=chat_id, **args)
    return format_search_results(events, args.get("keyword"))


FUNCTION_REGISTRY = {
    "add_event": _exec_add_event,
    "delete_event": _exec_delete_event,
    "delete_events_by_range": _exec_delete_events_by_range,
    "edit_event": _exec_edit_event,
    "get_today_events": _exec_get_today_events,
    "get_week_events": _exec_get_week_events,
    "search_events": _exec_search_events,
}


# ── Natural Language Message Handler ──────────────────────────────

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_message = update.message.text

    if not calendar_service.is_authenticated(chat_id):
        await update.message.reply_text("먼저 /start 로 인증을 완료해주세요.")
        return

    result = await nlp_service.process_message(user_message, chat_id)

    if result["type"] == "text_response":
        await update.message.reply_text(result["content"])
        return

    if result["type"] == "error":
        await update.message.reply_text(result["content"])
        return

    # Function call
    fn_name = result["function_name"]
    args = result["arguments"]
    tool_call_id = result.get("tool_call_id")

    executor = FUNCTION_REGISTRY.get(fn_name)
    if not executor:
        logger.warning("Unknown function: %s", fn_name)
        await update.message.reply_text("지원하지 않는 기능입니다.")
        return

    try:
        reply = await executor(chat_id, args)
        # Feed execution result back into conversation history
        if tool_call_id:
            nlp_service.add_tool_result(chat_id, tool_call_id, reply)
        await update.message.reply_text(reply)
    except Exception:
        logger.exception("Error executing %s", fn_name)
        if tool_call_id:
            nlp_service.add_tool_result(chat_id, tool_call_id, "처리 중 오류가 발생했습니다.")
        await update.message.reply_text("처리 중 오류가 발생했습니다.")


# ── Formatters ────────────────────────────────────────────────────

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


def format_week_events(events: list[dict]) -> str:
    if not events:
        return "📭 이번 주는 예정된 일정이 없습니다."

    lines = ["📅 이번 주 일정:\n"]
    current_date = ""
    for event in events:
        summary = event.get("summary", "(제목 없음)")
        start = event.get("start", {})

        if "dateTime" in start:
            dt_str = start["dateTime"][:10]
            time_str = start["dateTime"][11:16]
        else:
            dt_str = start.get("date", "")
            time_str = "종일"

        if dt_str != current_date:
            current_date = dt_str
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%d")
                weekday = WEEKDAY_NAMES[dt.weekday()]
                lines.append(f"\n📆 {dt_str} ({weekday})")
            except ValueError:
                lines.append(f"\n📆 {dt_str}")

        lines.append(f"  🕐 {time_str} - {summary}")

    return "\n".join(lines)


def format_search_results(events: list[dict], keyword: str | None = None) -> str:
    if not events:
        msg = "🔍 검색 결과가 없습니다."
        if keyword:
            msg += f' ("{keyword}")'
        return msg

    header = "🔍 검색 결과"
    if keyword:
        header += f' "{keyword}"'
    header += f" ({len(events)}건):\n"

    lines = [header]
    for i, event in enumerate(events, 1):
        summary = event.get("summary", "(제목 없음)")
        start = event.get("start", {})

        if "dateTime" in start:
            date_str = start["dateTime"][:10]
            time_str = start["dateTime"][11:16]
            lines.append(f"{i}. 📅 {date_str} 🕐 {time_str} - {summary}")
        else:
            date_str = start.get("date", "")
            lines.append(f"{i}. 📅 {date_str} 종일 - {summary}")

    return "\n".join(lines)


# ── Error & Registration ─────────────────────────────────────────

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
