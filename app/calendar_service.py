import asyncio
import calendar as cal
import logging
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    GOOGLE_SCOPES,
    SHARED_CALENDAR_ID,
    TIMEZONE,
    TIMEZONE_STR,
    TOKENS_DIR,
)

logger = logging.getLogger(__name__)


# ── Token & Auth Helpers ──────────────────────────────────────────

def _token_path(chat_id: int) -> Path:
    return TOKENS_DIR / f"{chat_id}.json"


def _create_flow() -> Flow:
    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI],
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=GOOGLE_SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )


def get_auth_url(chat_id: int) -> str:
    flow = _create_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=str(chat_id),
    )
    return auth_url


def _load_credentials(chat_id: int) -> Credentials | None:
    path = _token_path(chat_id)
    if not path.exists():
        return None

    creds = Credentials.from_authorized_user_file(str(path), GOOGLE_SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _save_credentials(chat_id, creds)
            except RefreshError:
                logger.warning("Token refresh failed for chat_id=%s, deleting token", chat_id)
                path.unlink(missing_ok=True)
                return None
        else:
            logger.warning("No refresh token for chat_id=%s, deleting token", chat_id)
            path.unlink(missing_ok=True)
            return None

    return creds


def _save_credentials(chat_id: int, creds: Credentials) -> None:
    path = _token_path(chat_id)
    path.write_text(creds.to_json())


def is_authenticated(chat_id: int) -> bool:
    return _token_path(chat_id).exists()


def get_all_authenticated_chat_ids() -> list[int]:
    return [
        int(p.stem)
        for p in TOKENS_DIR.glob("*.json")
        if p.stem.isdigit()
    ]


def _get_any_valid_creds() -> Credentials | None:
    for cid in get_all_authenticated_chat_ids():
        creds = _load_credentials(cid)
        if creds is not None:
            return creds
    return None


# ── Authentication ────────────────────────────────────────────────

def _check_calendar_access_sync(creds: Credentials) -> tuple[bool, str]:
    try:
        service = build("calendar", "v3", credentials=creds)
        calendar = service.calendars().get(calendarId=SHARED_CALENDAR_ID).execute()
        calendar_name = calendar.get("summary", SHARED_CALENDAR_ID)
        return True, calendar_name
    except HttpError as e:
        if e.resp.status in (403, 404):
            return False, (
                "공유 캘린더에 접근할 수 없습니다.\n\n"
                "캘린더 관리자에게 다음을 요청하세요:\n"
                '1. 공유 캘린더 설정 열기\n'
                '2. "특정 사용자와 공유" 섹션\n'
                "3. 귀하의 이메일 추가\n"
                '4. 권한: "일정 변경" 이상 부여'
            )
        return False, f"Google API 오류: {e.resp.status}"


def _authenticate_user_sync(auth_code: str) -> tuple[Credentials | None, str]:
    try:
        flow = _create_flow()
        flow.fetch_token(code=auth_code)
        creds = flow.credentials
        return creds, ""
    except Exception as e:
        logger.exception("Token exchange failed")
        return None, f"인증 코드 교환 실패: {e}"


async def authenticate_user(chat_id: int, auth_code: str) -> tuple[bool, str]:
    creds, error = await asyncio.to_thread(_authenticate_user_sync, auth_code)
    if creds is None:
        return False, error

    has_access, message = await asyncio.to_thread(_check_calendar_access_sync, creds)
    if not has_access:
        return False, message

    _save_credentials(chat_id, creds)
    return True, f"공유 캘린더 '{message}'에 연결되었습니다."


# ── Add Event ─────────────────────────────────────────────────────

async def add_event(
    chat_id: int,
    title: str,
    date: str,
    start_time: str,
    end_time: str | None = None,
    description: str | None = None,
) -> tuple[bool, str]:
    creds = await asyncio.to_thread(_load_credentials, chat_id)
    if creds is None:
        return False, "인증이 만료되었습니다. /start로 다시 인증해주세요."

    def _insert():
        start_dt = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
        if end_time:
            end_dt = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
        else:
            end_dt = start_dt + timedelta(hours=1)

        event_body = {
            "summary": title,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE_STR},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE_STR},
        }
        if description:
            event_body["description"] = description

        service = build("calendar", "v3", credentials=creds)
        event = service.events().insert(
            calendarId=SHARED_CALENDAR_ID, body=event_body
        ).execute()
        return event.get("htmlLink", "")

    try:
        link = await asyncio.to_thread(_insert)
        return True, link
    except HttpError as e:
        if e.resp.status == 403:
            return False, "캘린더 접근 권한이 없습니다."
        return False, f"Google API 오류: {e.resp.status}"
    except Exception:
        logger.exception("Unexpected error in add_event")
        return False, "알 수 없는 오류가 발생했습니다."


# ── Delete Event ──────────────────────────────────────────────────

async def delete_event(
    chat_id: int,
    title: str,
    date: str,
    original_time: str | None = None,
) -> tuple[bool, str]:
    creds = await asyncio.to_thread(_load_credentials, chat_id)
    if creds is None:
        return False, "인증이 만료되었습니다. /start로 다시 인증해주세요."

    def _delete():
        events = _find_events_by_date(creds, date)
        matched = _match_event(events, title, original_time)
        if not matched:
            return None, "해당 날짜에 일치하는 일정을 찾을 수 없습니다."

        service = build("calendar", "v3", credentials=creds)
        service.events().delete(
            calendarId=SHARED_CALENDAR_ID, eventId=matched["id"]
        ).execute()
        return matched.get("summary", title), None

    try:
        deleted_title, error = await asyncio.to_thread(_delete)
        if error:
            return False, error
        return True, deleted_title
    except HttpError as e:
        if e.resp.status == 403:
            return False, "캘린더 접근 권한이 없습니다."
        return False, f"Google API 오류: {e.resp.status}"
    except Exception:
        logger.exception("Unexpected error in delete_event")
        return False, "알 수 없는 오류가 발생했습니다."


# ── Edit Event ────────────────────────────────────────────────────

async def edit_event(
    chat_id: int,
    title: str,
    date: str,
    changes: dict,
    original_time: str | None = None,
) -> tuple[bool, str]:
    creds = await asyncio.to_thread(_load_credentials, chat_id)
    if creds is None:
        return False, "인증이 만료되었습니다. /start로 다시 인증해주세요."

    def _update():
        events = _find_events_by_date(creds, date)
        matched = _match_event(events, title, original_time)
        if not matched:
            return None, "해당 날짜에 일치하는 일정을 찾을 수 없습니다."

        # Apply changes
        if changes.get("title"):
            matched["summary"] = changes["title"]

        # Handle date/time changes
        new_date = changes.get("date") or date
        current_start = matched.get("start", {})
        current_end = matched.get("end", {})

        if changes.get("start_time"):
            start_dt = datetime.strptime(
                f"{new_date} {changes['start_time']}", "%Y-%m-%d %H:%M"
            )
            matched["start"] = {
                "dateTime": start_dt.isoformat(),
                "timeZone": TIMEZONE_STR,
            }
            # If no new end_time, set end = start + 1h
            if not changes.get("end_time"):
                end_dt = start_dt + timedelta(hours=1)
                matched["end"] = {
                    "dateTime": end_dt.isoformat(),
                    "timeZone": TIMEZONE_STR,
                }
        elif changes.get("date"):
            # Date changed but time unchanged — shift the date
            if "dateTime" in current_start:
                old_time = current_start["dateTime"][11:16]
                start_dt = datetime.strptime(
                    f"{new_date} {old_time}", "%Y-%m-%d %H:%M"
                )
                matched["start"] = {
                    "dateTime": start_dt.isoformat(),
                    "timeZone": TIMEZONE_STR,
                }
            if "dateTime" in current_end:
                old_time = current_end["dateTime"][11:16]
                end_dt = datetime.strptime(
                    f"{new_date} {old_time}", "%Y-%m-%d %H:%M"
                )
                matched["end"] = {
                    "dateTime": end_dt.isoformat(),
                    "timeZone": TIMEZONE_STR,
                }

        if changes.get("end_time"):
            end_dt = datetime.strptime(
                f"{new_date} {changes['end_time']}", "%Y-%m-%d %H:%M"
            )
            matched["end"] = {
                "dateTime": end_dt.isoformat(),
                "timeZone": TIMEZONE_STR,
            }

        if changes.get("description"):
            matched["description"] = changes["description"]

        service = build("calendar", "v3", credentials=creds)
        updated = service.events().update(
            calendarId=SHARED_CALENDAR_ID,
            eventId=matched["id"],
            body=matched,
        ).execute()
        return updated.get("summary", title), None

    try:
        updated_title, error = await asyncio.to_thread(_update)
        if error:
            return False, error
        return True, updated_title
    except HttpError as e:
        if e.resp.status == 403:
            return False, "캘린더 접근 권한이 없습니다."
        return False, f"Google API 오류: {e.resp.status}"
    except Exception:
        logger.exception("Unexpected error in edit_event")
        return False, "알 수 없는 오류가 발생했습니다."


# ── Query Events ──────────────────────────────────────────────────

async def get_today_events() -> list[dict]:
    creds = await asyncio.to_thread(_get_any_valid_creds)
    if creds is None:
        logger.warning("No valid credentials found for get_today_events")
        return []

    def _list():
        now = datetime.now(TIMEZONE)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)

        service = build("calendar", "v3", credentials=creds)
        result = service.events().list(
            calendarId=SHARED_CALENDAR_ID,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return result.get("items", [])

    try:
        return await asyncio.to_thread(_list)
    except Exception:
        logger.exception("Unexpected error in get_today_events")
        return []


async def get_week_events() -> list[dict]:
    creds = await asyncio.to_thread(_get_any_valid_creds)
    if creds is None:
        logger.warning("No valid credentials found for get_week_events")
        return []

    def _list():
        now = datetime.now(TIMEZONE)
        # Monday of this week
        start_of_week = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_of_week = (start_of_week + timedelta(days=6)).replace(
            hour=23, minute=59, second=59, microsecond=0
        )

        service = build("calendar", "v3", credentials=creds)
        result = service.events().list(
            calendarId=SHARED_CALENDAR_ID,
            timeMin=start_of_week.isoformat(),
            timeMax=end_of_week.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return result.get("items", [])

    try:
        return await asyncio.to_thread(_list)
    except Exception:
        logger.exception("Unexpected error in get_week_events")
        return []


async def search_events(
    chat_id: int,
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    creds = await asyncio.to_thread(_load_credentials, chat_id)
    if creds is None:
        return []

    def _search():
        now = datetime.now(TIMEZONE)

        if date_from:
            time_min = _safe_parse_date(date_from).replace(tzinfo=TIMEZONE)
        else:
            time_min = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if date_to:
            time_max = _safe_parse_date(date_to).replace(
                hour=23, minute=59, second=59, tzinfo=TIMEZONE
            )
        else:
            time_max = time_min + timedelta(days=30)

        service = build("calendar", "v3", credentials=creds)
        params = {
            "calendarId": SHARED_CALENDAR_ID,
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if keyword:
            params["q"] = keyword

        result = service.events().list(**params).execute()
        return result.get("items", [])

    try:
        return await asyncio.to_thread(_search)
    except Exception:
        logger.exception("Unexpected error in search_events")
        return []


# ── Internal Helpers ──────────────────────────────────────────────

def _safe_parse_date(date_str: str) -> datetime:
    """Parse YYYY-MM-DD, clamping invalid days to the last day of the month."""
    parts = date_str.split("-")
    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    max_day = cal.monthrange(year, month)[1]
    day = min(day, max_day)
    return datetime(year, month, day)


def _find_events_by_date(creds: Credentials, date: str) -> list[dict]:
    start_of_day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=TIMEZONE)
    end_of_day = start_of_day.replace(hour=23, minute=59, second=59)

    service = build("calendar", "v3", credentials=creds)
    result = service.events().list(
        calendarId=SHARED_CALENDAR_ID,
        timeMin=start_of_day.isoformat(),
        timeMax=end_of_day.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])


async def delete_events_by_range(
    chat_id: int,
    date_from: str,
    date_to: str,
    keyword: str | None = None,
) -> tuple[int, str]:
    """Delete all events in a date range. Returns (count_deleted, error_message)."""
    creds = await asyncio.to_thread(_load_credentials, chat_id)
    if creds is None:
        return 0, "인증이 만료되었습니다. /start로 다시 인증해주세요."

    def _bulk_delete():
        time_min = _safe_parse_date(date_from).replace(tzinfo=TIMEZONE)
        time_max = _safe_parse_date(date_to).replace(
            hour=23, minute=59, second=59, tzinfo=TIMEZONE
        )

        service = build("calendar", "v3", credentials=creds)
        params = {
            "calendarId": SHARED_CALENDAR_ID,
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if keyword:
            params["q"] = keyword

        result = service.events().list(**params).execute()
        events = result.get("items", [])

        if not events:
            return 0, "해당 기간에 일정이 없습니다."

        deleted = 0
        for event in events:
            service.events().delete(
                calendarId=SHARED_CALENDAR_ID, eventId=event["id"]
            ).execute()
            deleted += 1

        return deleted, ""

    try:
        count, error = await asyncio.to_thread(_bulk_delete)
        return count, error
    except HttpError as e:
        if e.resp.status == 403:
            return 0, "캘린더 접근 권한이 없습니다."
        return 0, f"Google API 오류: {e.resp.status}"
    except Exception:
        logger.exception("Unexpected error in delete_events_by_range")
        return 0, "알 수 없는 오류가 발생했습니다."


def _match_event(events: list[dict], title: str, start_time: str | None = None) -> dict | None:
    """Match an event by title, then by start time, then by single-event fallback."""
    if not events:
        return None

    # 1. Try title match
    title_lower = title.lower()
    for event in events:
        summary = event.get("summary", "").lower()
        if title_lower in summary or summary in title_lower:
            return event

    # 2. Try start time match
    if start_time:
        for event in events:
            event_start = event.get("start", {}).get("dateTime", "")
            if event_start and event_start[11:16] == start_time:
                return event

    # 3. If only one event on that day, use it
    if len(events) == 1:
        return events[0]

    return None
