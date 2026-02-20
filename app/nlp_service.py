import json
import logging
from datetime import datetime

from openai import AsyncOpenAI, APIError

from app.config import OPENAI_API_KEY, OPENAI_MODEL, TIMEZONE
from app.prompts import SYSTEM_PROMPT, TOOLS

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ── Chat History ─────────────────────────────────────────────────

MAX_HISTORY = 100  # max messages per chat (FIFO)
_chat_histories: dict[int, list[dict]] = {}


def _get_history(chat_id: int) -> list[dict]:
    return _chat_histories.setdefault(chat_id, [])


def _trim_history(chat_id: int) -> None:
    hist = _chat_histories.get(chat_id)
    if hist and len(hist) > MAX_HISTORY:
        _chat_histories[chat_id] = hist[-MAX_HISTORY:]


def add_user_message(chat_id: int, content: str) -> None:
    _get_history(chat_id).append({"role": "user", "content": content})
    _trim_history(chat_id)


def add_assistant_tool_call(chat_id: int, tool_call_raw: dict) -> None:
    """Store the assistant message that contains tool_calls."""
    _get_history(chat_id).append({
        "role": "assistant",
        "tool_calls": [tool_call_raw],
    })
    _trim_history(chat_id)


def add_tool_result(chat_id: int, tool_call_id: str, content: str) -> None:
    """Store the tool execution result so GPT can reference it later."""
    _get_history(chat_id).append({
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    })
    _trim_history(chat_id)


def add_assistant_message(chat_id: int, content: str) -> None:
    _get_history(chat_id).append({"role": "assistant", "content": content})
    _trim_history(chat_id)


# ── Public API ────────────────────────────────────────────────────

def _build_messages(chat_id: int) -> list[dict]:
    today = datetime.now(TIMEZONE)
    today_str = today.strftime("%Y-%m-%d")
    weekday_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    today_weekday = weekday_names[today.weekday()]
    system = SYSTEM_PROMPT.format(today=today_str, weekday=today_weekday)
    return [{"role": "developer", "content": system}] + _get_history(chat_id)


async def process_message(user_message: str, chat_id: int) -> dict:
    add_user_message(chat_id, user_message)
    messages = _build_messages(chat_id)

    try:
        response = await _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_completion_tokens=500,
            reasoning_effort="medium",
        )

        message = response.choices[0].message

        if message.tool_calls:
            tool_call = message.tool_calls[0]

            # Store assistant tool_call in history
            add_assistant_tool_call(chat_id, {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            })

            return {
                "type": "function_call",
                "function_name": tool_call.function.name,
                "arguments": json.loads(tool_call.function.arguments),
                "tool_call_id": tool_call.id,
            }
        else:
            content = message.content or "무엇을 도와드릴까요?"
            add_assistant_message(chat_id, content)
            return {
                "type": "text_response",
                "content": content,
            }

    except APIError as e:
        logger.error("OpenAI API error: %s", e)
        return {"type": "error", "content": "AI 서비스에 일시적인 오류가 발생했습니다."}
    except Exception:
        logger.exception("Unexpected error in process_message")
        return {"type": "error", "content": "메시지 처리 중 오류가 발생했습니다."}


async def get_followup_response(chat_id: int, filter_instruction: str | None = None) -> str:
    """Call GPT again after tool result to compose a natural response."""
    messages = _build_messages(chat_id)
    if filter_instruction:
        messages.append({"role": "user", "content": filter_instruction})

    try:
        response = await _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_completion_tokens=5000,
            reasoning_effort="medium",
        )
        content = response.choices[0].message.content or "결과를 처리할 수 없습니다."
        add_assistant_message(chat_id, content)
        return content
    except Exception:
        logger.exception("Error in get_followup_response")
        return "결과를 처리하는 중 오류가 발생했습니다."
