import calendar as cal
import logging
from datetime import datetime, timedelta

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app import calendar_service, geo_service, nlp_service

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

    auth_url = calendar_service.get_auth_url(chat_id)
    await update.message.reply_text(
        "안녕하세요! 📅 캘린더 봇입니다.\n\n"
        "Google 계정을 연동하려면 아래 링크를 열어주세요:\n\n"
        f"{auth_url}\n\n"
        "권한을 허용하면 자동으로 인증이 완료됩니다!"
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


async def _exec_add_events_by_range(chat_id: int, args: dict) -> str:
    count, error = await calendar_service.add_events_by_range(chat_id=chat_id, **args)
    if count > 0:
        time_str = args["start_time"]
        if args.get("end_time"):
            time_str += f" - {args['end_time']}"
        msg = f"✅ {count}개 일정이 추가되었습니다!\n\n📅 {args['date_from']} ~ {args['date_to']}\n🕐 {time_str}\n📝 {args['title']}"
        if args.get("description"):
            msg += f"\n💬 {args['description']}"
        return msg
    return f"❌ 일정 추가 실패\n{error}"


async def _exec_add_multiday_event(chat_id: int, args: dict) -> str:
    success, result = await calendar_service.add_multiday_event(chat_id=chat_id, **args)
    if success:
        reply = f"✅ 일정이 추가되었습니다!\n\n📅 {args['date_from']} ~ {args['date_to']}\n📝 {args['title']}"
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


# ── Navigation ───────────────────────────────────────────────────

# Pending navigation: chat_id -> {"destination": str, "lat": float, "lng": float, "address": str}
_pending_navigation: dict[int, dict] = {}


async def _exec_navigate(chat_id: int, args: dict) -> str:
    destination = args.get("destination", "")
    if not destination:
        return "목적지를 알려주세요."

    result = await geo_service.geocode(destination)
    if result is None:
        return f"'{destination}'의 위치를 찾을 수 없습니다. 더 구체적인 주소나 장소명을 알려주세요."

    _pending_navigation[chat_id] = {
        "destination": destination,
        "lat": result["lat"],
        "lng": result["lng"],
        "address": result["address"],
    }
    return f"📍 '{destination}' 위치를 찾았습니다!\n({result['address']})\n\n아래 버튼을 눌러 현재 위치를 공유해주세요."


async def _exec_navigate_to_event(chat_id: int, args: dict) -> str:
    events = await calendar_service.get_today_events()
    if not events:
        return "오늘 예정된 일정이 없습니다."

    title_filter = args.get("title", "")
    now = datetime.now()

    target = None
    for event in events:
        summary = event.get("summary", "")
        location = event.get("location", "")
        if not location:
            continue

        # If title filter is given, match it
        if title_filter and title_filter not in summary:
            continue

        # If no title filter, pick the nearest upcoming event
        if not title_filter:
            start = event.get("start", {})
            if "dateTime" in start:
                event_time = datetime.fromisoformat(start["dateTime"])
                if event_time < now:
                    continue
        target = event
        break

    if target is None:
        if title_filter:
            return f"'{title_filter}' 일정을 찾을 수 없거나 장소 정보가 없습니다."
        return "장소 정보가 있는 다음 일정을 찾을 수 없습니다."

    location = target["location"]
    summary = target.get("summary", "(제목 없음)")
    _, time_str = _event_time(target)

    result = await geo_service.geocode(location)
    if result is None:
        return f"'{location}'의 위치를 찾을 수 없습니다."

    _pending_navigation[chat_id] = {
        "destination": location,
        "lat": result["lat"],
        "lng": result["lng"],
        "address": result["address"],
    }
    return (
        f"📅 {summary} ({time_str})\n"
        f"📍 '{location}' 위치를 찾았습니다!\n({result['address']})\n\n"
        f"아래 버튼을 눌러 현재 위치를 공유해주세요."
    )


FUNCTION_REGISTRY = {
    "add_event": _exec_add_event,
    "add_events_by_range": _exec_add_events_by_range,
    "add_multiday_event": _exec_add_multiday_event,
    "delete_event": _exec_delete_event,
    "delete_events_by_range": _exec_delete_events_by_range,
    "edit_event": _exec_edit_event,
    "get_today_events": _exec_get_today_events,
    "get_week_events": _exec_get_week_events,
    "search_events": _exec_search_events,
    "navigate": _exec_navigate,
    "navigate_to_event": _exec_navigate_to_event,
}

_MUTATION_FUNCTIONS = {"add_event", "add_events_by_range", "add_multiday_event", "delete_event", "delete_events_by_range", "edit_event"}
_QUERY_FUNCTIONS = {"get_today_events", "get_week_events", "search_events"}
_NAVIGATION_FUNCTIONS = {"navigate", "navigate_to_event"}


def _extract_month_range(fn_name: str, args: dict) -> tuple[str, str] | None:
    """Return (YYYY-MM-DD, YYYY-MM-DD) for the month affected by a mutation."""
    if fn_name in ("delete_events_by_range", "add_events_by_range", "add_multiday_event"):
        date_str = args.get("date_from", "")
    elif fn_name == "edit_event":
        # If the date was changed, show the new month
        date_str = args.get("changes", {}).get("date") or args.get("date", "")
    else:
        date_str = args.get("date", "")

    if not date_str or len(date_str) < 7:
        return None

    try:
        year, month = int(date_str[:4]), int(date_str[5:7])
        last_day = cal.monthrange(year, month)[1]
        return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day:02d}"
    except (ValueError, IndexError):
        return None


async def _get_month_summary(chat_id: int, fn_name: str, args: dict) -> str | None:
    """Fetch and format the affected month's events after a mutation."""
    month_range = _extract_month_range(fn_name, args)
    if not month_range:
        return None

    date_from, date_to = month_range
    try:
        events = await calendar_service.search_events(
            chat_id=chat_id, date_from=date_from, date_to=date_to
        )
    except Exception:
        logger.exception("Error fetching month summary")
        return None

    month_label = f"{date_from[:4]}년 {int(date_from[5:7])}월"

    if not events:
        return f"\n📋 {month_label} 전체 일정: 없음"

    lines = [f"\n📋 {month_label} 전체 일정 ({len(events)}건):"]
    current_date = ""
    for event in events:
        summary = event.get("summary", "(제목 없음)")
        dt_str, time_str = _event_time(event)

        if dt_str != current_date:
            current_date = dt_str
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%d")
                weekday = WEEKDAY_NAMES[dt.weekday()]
                lines.append(f"\n  📆 {dt_str} ({weekday})")
            except ValueError:
                lines.append(f"\n  📆 {dt_str}")

        lines.append(f"    🕐 {time_str} - {summary}")

    return "\n".join(lines)


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

        if fn_name in _NAVIGATION_FUNCTIONS and chat_id in _pending_navigation:
            keyboard = ReplyKeyboardMarkup(
                [[KeyboardButton("📍 현재 위치 공유", request_location=True)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            )
            await update.message.reply_text(reply, reply_markup=keyboard)
        elif fn_name in _QUERY_FUNCTIONS:
            # Let GPT analyze results and compose a natural response
            gpt_reply = await nlp_service.get_followup_response(chat_id)
            await update.message.reply_text(gpt_reply)
        else:
            await update.message.reply_text(reply)

            # After mutation, show the affected month's events
            if fn_name in _MUTATION_FUNCTIONS:
                month_summary = await _get_month_summary(chat_id, fn_name, args)
                if month_summary:
                    await update.message.reply_text(month_summary)
    except Exception:
        logger.exception("Error executing %s", fn_name)
        if tool_call_id:
            nlp_service.add_tool_result(chat_id, tool_call_id, "처리 중 오류가 발생했습니다.")
        await update.message.reply_text("처리 중 오류가 발생했습니다.")


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle location shared by user (for navigation flow)."""
    chat_id = update.effective_chat.id
    location = update.message.location

    pending = _pending_navigation.pop(chat_id, None)
    if pending is None:
        await update.message.reply_text(
            "길찾기 요청이 없습니다. 먼저 목적지를 알려주세요.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    url = geo_service.build_directions_url(
        start_lat=location.latitude,
        start_lng=location.longitude,
        dest_lat=pending["lat"],
        dest_lng=pending["lng"],
        dest_name=pending["destination"],
    )

    await update.message.reply_text(
        f"🗺️ {pending['destination']} 길찾기\n\n"
        f"📍 출발: 현재 위치\n"
        f"📍 도착: {pending['address']}\n\n"
        f"👉 {url}",
        reply_markup=ReplyKeyboardRemove(),
    )


# ── Formatters ────────────────────────────────────────────────────

def _event_time(event: dict) -> tuple[str, str]:
    """Return (date_str, time_str) for any event type."""
    start = event.get("start", {})
    if "dateTime" in start:
        return start["dateTime"][:10], start["dateTime"][11:16]
    # All-day event
    start_date = start.get("date", "")
    end_date = event.get("end", {}).get("date", "")
    if start_date and end_date:
        try:
            s = datetime.strptime(start_date, "%Y-%m-%d")
            e = datetime.strptime(end_date, "%Y-%m-%d")
            if (e - s).days > 1:
                actual_end = (e - timedelta(days=1)).strftime("%m-%d")
                return start_date, f"{start_date[5:]}~{actual_end} 종일"
        except ValueError:
            pass
    return start_date, "종일"


def format_today_events(events: list[dict]) -> str:
    if not events:
        return "📭 오늘은 예정된 일정이 없습니다."

    lines = ["📅 오늘의 일정:\n"]
    for i, event in enumerate(events, 1):
        summary = event.get("summary", "(제목 없음)")
        _, time_str = _event_time(event)
        lines.append(f"{i}. 🕐 {time_str} - {summary}")

    return "\n".join(lines)


def format_week_events(events: list[dict]) -> str:
    if not events:
        return "📭 이번 주는 예정된 일정이 없습니다."

    lines = ["📅 이번 주 일정:\n"]
    current_date = ""
    for event in events:
        summary = event.get("summary", "(제목 없음)")
        dt_str, time_str = _event_time(event)

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
        date_str, time_str = _event_time(event)
        lines.append(f"{i}. 📅 {date_str} 🕐 {time_str} - {summary}")

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
    application.add_handler(
        MessageHandler(filters.LOCATION, handle_location)
    )
    application.add_error_handler(error_handler)
