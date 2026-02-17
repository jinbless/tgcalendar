"""GPT function schemas and system prompt for calendar assistant.

Edit SYSTEM_PROMPT and TOOLS here to tune GPT behavior
without touching the bot logic in nlp_service.py.
"""

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
            "name": "add_events_by_range",
            "description": "날짜 구간에 【시간이 있는】 일정을 날짜마다 별도로 추가합니다(N개 이벤트 생성). '24일~26일 오전 9시 회의', '월~금 매일 10시 스탠드업' 등 반복 미팅에 사용하세요. ⚠️ 시간이 없는 출장/휴가/연차는 add_multiday_event를 쓰세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "일정 제목"},
                    "date_from": {"type": "string", "description": "시작 날짜 (YYYY-MM-DD)"},
                    "date_to": {"type": "string", "description": "종료 날짜 (YYYY-MM-DD)"},
                    "start_time": {"type": "string", "description": "시작 시간 (HH:MM 형식, 24시간)"},
                    "end_time": {"type": "string", "description": "종료 시간 (HH:MM 형식, 24시간). 언급 없으면 생략"},
                    "description": {"type": "string", "description": "일정 설명. 언급 없으면 생략"},
                },
                "required": ["title", "date_from", "date_to", "start_time"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_multiday_event",
            "description": "날짜 구간 전체를 아우르는 【종일(시간 없음) 단일 이벤트 1개】를 추가합니다. 출장, 휴가, 여행, 연차 등 기간 일정에 사용하세요. 예: '2/28~3/10 브라질 출장', '다음주 월~금 연차'. ⚠️ 시간이 언급된 경우(예: 오전 9시)는 add_events_by_range를 쓰세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "일정 제목"},
                    "date_from": {"type": "string", "description": "시작 날짜 (YYYY-MM-DD)"},
                    "date_to": {"type": "string", "description": "종료 날짜 (YYYY-MM-DD)"},
                    "description": {"type": "string", "description": "일정 설명. 언급 없으면 생략"},
                },
                "required": ["title", "date_from", "date_to"],
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
            "name": "delete_events_by_range",
            "description": "특정 기간의 일정을 일괄 삭제합니다. '2월 일정 다 지워줘', '이번 주 일정 전부 삭제' 등에 호출하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "삭제 시작일 (YYYY-MM-DD)"},
                    "date_to": {"type": "string", "description": "삭제 종료일 (YYYY-MM-DD). 월 단위 시 해당 월 마지막 날"},
                    "keyword": {"type": "string", "description": "특정 키워드 일정만 삭제. 전부 삭제 시 생략"},
                },
                "required": ["date_from", "date_to"],
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
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "길찾기를 제공합니다. 직접 장소명/주소를 지정하거나, 이전 대화의 캘린더 일정 장소로 이동할 때 사용하세요. 직접 장소를 말한 경우 destination 입력. '4번 일정 길찾기', '그 일정 가는 법'처럼 이전 대화의 일정을 참조하는 경우 title과 date 입력.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {
                        "type": "string",
                        "description": "직접 지정 목적지 이름 또는 주소. 예: '강남역', '서울역'. 사용자가 장소명/주소를 직접 말한 경우에만 입력",
                    },
                    "title": {
                        "type": "string",
                        "description": "캘린더 일정 제목 또는 키워드. 이전 대화의 일정을 참조하는 경우 해당 일정 제목 입력",
                    },
                    "date": {
                        "type": "string",
                        "description": "일정 날짜 (YYYY-MM-DD 형식). 이전 대화의 일정을 참조하는 경우 입력",
                    },
                },
                "required": [],
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
- 월 단위 검색 시 date_to는 해당 월의 마지막 날로 설정하세요. (2월 → 2월 28일 또는 29일)
- 이전 대화에서 조회한 일정 결과를 참고하여 사용자가 "그거", "첫 번째", "그 회의" 등으로 지칭하는 일정을 파악하세요.
- 사용자가 이전 조회 결과의 일정을 수정/삭제하려 할 때, 해당 일정의 제목/날짜/시간을 정확히 추출하세요.
- 범위 삭제 요청("2월 일정 다 지워줘", "이번 주 일정 전부 삭제")에는 delete_events_by_range를 사용하세요.
- 사용자가 특정 날짜+시간의 기존 일정을 언급하면서 수정/삭제를 요청하면, 새 일정 추가가 아닌 edit_event 또는 delete_event를 호출하세요.
- 출장, 휴가, 여행 등 기간 일정은 add_multiday_event를 사용하세요 (종일 단일 이벤트).
- 매일 같은 시간에 반복되는 일정(회의, 스탠드업 등)은 add_events_by_range를 사용하세요.
- 길찾기 요청은 항상 navigate 함수를 호출하세요. 사용자가 장소명/주소를 직접 말하면 destination 파라미터에 입력하고, 이전 대화의 일정을 참조하면("N번 일정 길찾기", "그 일정 가는 법" 등) 해당 일정의 제목과 날짜를 title/date 파라미터에 입력하세요.
- 일정 조회 결과에는 제목, 시간, 장소(📍), 설명(💬) 정보가 포함됩니다. 사용자가 장소를 물어보면 이 정보를 활용하세요.
- 일정에 별도 장소(📍) 정보가 없더라도, 제목이나 설명에 장소명이 포함되어 있으면 그것을 장소로 인식하여 안내하세요. 예: "신규감독관 교육(고용노동교육원)" → 장소는 "고용노동교육원"."""
