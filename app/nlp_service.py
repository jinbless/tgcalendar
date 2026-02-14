import json
import logging
from datetime import datetime

from openai import AsyncOpenAI, APIError

from app.config import OPENAI_API_KEY, OPENAI_MODEL, TIMEZONE

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ── Function Schemas (Tools) ─────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_event",
            "description": "캘린더에 새 일정을 추가합니다. 사용자가 일정 추가를 요청할 때 호출하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "일정 제목"},
                    "date": {"type": "string", "description": "날짜 (YYYY-MM-DD 형식). 상대 날짜는 절대 날짜로 변환"},
                    "start_time": {"type": "string", "description": "시작 시간 (HH:MM 형식, 24시간)"},
                    "end_time": {"type": "string", "description": "종료 시간 (HH:MM 형식, 24시간). 언급 없으면 생략"},
                    "description": {"type": "string", "description": "일정 설명. 언급 없으면 생략"},
                },
                "required": ["title", "date", "start_time"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_event",
            "description": "캘린더에서 일정을 삭제합니다. 사용자가 삭제/취소/지워줘 등을 요청할 때 호출하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "삭제할 일정 제목 (부분 일치 가능). 제목을 모르면 빈 문자열"},
                    "date": {"type": "string", "description": "일정 날짜 (YYYY-MM-DD 형식)"},
                    "original_time": {"type": "string", "description": "기존 시작 시간 (HH:MM). 사용자가 시간으로 일정을 지칭한 경우"},
                },
                "required": ["title", "date"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_event",
            "description": "캘린더 일정을 수정합니다. 사용자가 변경/수정/바꿔/옮겨 등을 요청할 때 호출하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "수정할 일정 제목 (부분 일치 가능). 제목을 모르면 빈 문자열"},
                    "date": {"type": "string", "description": "현재 일정 날짜 (YYYY-MM-DD 형식)"},
                    "original_time": {"type": "string", "description": "기존 시작 시간 (HH:MM). 사용자가 시간으로 일정을 지칭한 경우"},
                    "changes": {
                        "type": "object",
                        "description": "변경할 내용. 변경하지 않는 항목은 생략",
                        "properties": {
                            "title": {"type": "string", "description": "새 제목"},
                            "date": {"type": "string", "description": "새 날짜 (YYYY-MM-DD)"},
                            "start_time": {"type": "string", "description": "새 시작 시간 (HH:MM)"},
                            "end_time": {"type": "string", "description": "새 종료 시간 (HH:MM)"},
                            "description": {"type": "string", "description": "새 설명"},
                        },
                        "additionalProperties": False,
                    },
                },
                "required": ["title", "date", "changes"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_events",
            "description": "오늘 일정을 조회합니다. '오늘 일정', '오늘 뭐 있어?' 등의 요청에 호출하세요.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_week_events",
            "description": "이번 주 일정을 조회합니다. '이번 주 일정', '주간 일정', '이번주 뭐 있어?' 등의 요청에 호출하세요.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": "일정을 검색합니다. 특정 기간이나 키워드로 일정을 찾을 때 호출하세요. 예: '3월 일정', '회의 검색', '다음 주 뭐 있어?'",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "검색 키워드. 없으면 생략"},
                    "date_from": {"type": "string", "description": "검색 시작일 (YYYY-MM-DD)"},
                    "date_to": {"type": "string", "description": "검색 종료일 (YYYY-MM-DD). 월 단위 검색 시 해당 월 마지막 날"},
                },
                "additionalProperties": False,
            },
        },
    },
]

SYSTEM_PROMPT = """당신은 캘린더 관리 어시스턴트입니다.
사용자의 한국어 요청을 분석하여 적절한 함수를 호출해주세요.

오늘 날짜: {today} ({weekday})

규칙:
- 상대적 날짜(내일, 다음주 월요일 등)는 오늘 날짜 기준으로 절대 날짜(YYYY-MM-DD)로 변환하세요.
- 시간은 24시간 형식(HH:MM)으로 변환하세요. (오후 3시 → 15:00)
- 일정과 관련 없는 일반 대화에는 함수를 호출하지 말고 직접 한국어로 응답하세요.
- 월 단위 검색 시 date_to는 해당 월의 마지막 날로 설정하세요. (2월 → 2월 28일 또는 29일)"""


# ── Public API ────────────────────────────────────────────────────

async def process_message(user_message: str) -> dict:
    today = datetime.now(TIMEZONE)
    today_str = today.strftime("%Y-%m-%d")
    weekday_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    today_weekday = weekday_names[today.weekday()]

    system = SYSTEM_PROMPT.format(today=today_str, weekday=today_weekday)

    try:
        response = await _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=500,
        )

        message = response.choices[0].message

        if message.tool_calls:
            tool_call = message.tool_calls[0]
            return {
                "type": "function_call",
                "function_name": tool_call.function.name,
                "arguments": json.loads(tool_call.function.arguments),
            }
        else:
            return {
                "type": "text_response",
                "content": message.content or "무엇을 도와드릴까요?",
            }

    except APIError as e:
        logger.error("OpenAI API error: %s", e)
        return {"type": "error", "content": "AI 서비스에 일시적인 오류가 발생했습니다."}
    except Exception:
        logger.exception("Unexpected error in process_message")
        return {"type": "error", "content": "메시지 처리 중 오류가 발생했습니다."}
