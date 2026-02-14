import asyncio
import json
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


def _token_path(chat_id: int) -> Path:
    return TOKENS_DIR / f"{chat_id}.json"


def _create_flow() -> Flow:
    client_config = {
        "installed": {
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


def get_auth_url() -> str:
    flow = _create_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
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


def _check_calendar_access_sync(creds: Credentials) -> tuple[bool, str]:
    """Verify the user has access to the shared calendar (synchronous)."""
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
    """Exchange auth code for credentials and check access (synchronous)."""
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
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": TIMEZONE_STR,
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": TIMEZONE_STR,
            },
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
    except Exception as e:
        logger.exception("Unexpected error in add_event")
        return False, "알 수 없는 오류가 발생했습니다."


async def get_today_events() -> list[dict]:
    # Find any valid credential to query the shared calendar
    chat_ids = get_all_authenticated_chat_ids()
    creds = None
    for cid in chat_ids:
        creds = await asyncio.to_thread(_load_credentials, cid)
        if creds is not None:
            break

    if creds is None:
        logger.warning("No valid credentials found for get_today_events")
        return []

    def _list_events():
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
        return await asyncio.to_thread(_list_events)
    except HttpError as e:
        logger.error("Failed to fetch today's events: %s", e)
        return []
    except Exception:
        logger.exception("Unexpected error in get_today_events")
        return []
