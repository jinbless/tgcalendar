import json
import logging
from datetime import datetime

from openai import AsyncOpenAI, APIError

from app.config import OPENAI_API_KEY, OPENAI_MODEL, TIMEZONE

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """당신은 캘린더 일정 정보를 추출하는 어시스턴트입니다.
사용자의 한국어 메시지에서 일정 정보를 추출하여 JSON으로 반환해주세요.

규칙:
1. 반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.
2. 날짜가 상대적이면 (내일, 다음주, 이번 주 금요일 등) 오늘 날짜를 기준으로 절대 날짜로 변환하세요.
3. 종료 시간이 언급되지 않으면 end_time은 null로 설정하세요.
4. 설명이 없으면 description은 null로 설정하세요.
5. 일정 관련 메시지가 아니면 {"error": "일정 관련 메시지가 아닙니다"} 를 반환하세요.

JSON 형식:
{
  "title": "일정 제목",
  "date": "YYYY-MM-DD",
  "start_time": "HH:MM",
  "end_time": "HH:MM 또는 null",
  "description": "설명 또는 null"
}"""


async def parse_event(user_message: str) -> dict | None:
    today = datetime.now(TIMEZONE)
    today_str = today.strftime("%Y-%m-%d")
    weekday_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    today_weekday = weekday_names[today.weekday()]

    user_prompt = f"오늘 날짜: {today_str} ({today_weekday})\n\n메시지: {user_message}"

    try:
        response = await _client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=300,
        )

        content = response.choices[0].message.content.strip()
        parsed = json.loads(content)

        if "error" in parsed:
            logger.info("NLP rejected message: %s", parsed["error"])
            return None

        required = ("title", "date", "start_time")
        if not all(parsed.get(k) for k in required):
            logger.warning("NLP response missing required fields: %s", content)
            return None

        return parsed

    except json.JSONDecodeError:
        logger.error("NLP returned invalid JSON: %s", content)
        return None
    except APIError as e:
        logger.error("OpenAI API error: %s", e)
        return None
    except Exception:
        logger.exception("Unexpected error in parse_event")
        return None
