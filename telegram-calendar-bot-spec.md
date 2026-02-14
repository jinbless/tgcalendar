# Telegram Calendar Bot 구현 가이드

## 프로젝트 개요
텔레그램 봇을 통해 자연어로 구글 캘린더 일정을 관리하고, 매일 오전 9시에 오늘의 일정을 알려주는 시스템을 구현합니다.

## 기술 스택
- **언어**: Python 3.11+
- **프레임워크**: python-telegram-bot, google-api-python-client, anthropic
- **배포**: Docker, DigitalOcean
- **스케줄링**: APScheduler

## 핵심 기능

### 1. 텔레그램 봇 통합
- `/start` 명령어로 봇 초기화 및 구글 계정 연동 안내
- 자연어 메시지 수신 (예: "내일 오후 3시에 팀 회의 일정 추가해줘")
- 일정 추가 성공/실패 피드백 전송

### 2. 자연어 처리 (Claude API)
- 사용자 메시지 분석
- 다음 정보 추출:
  - 일정 제목 (title)
  - 날짜 (date) - YYYY-MM-DD 형식
  - 시작 시간 (start_time) - HH:MM 형식
  - 종료 시간 (end_time, optional) - HH:MM 형식
  - 설명 (description, optional)
- JSON 형식으로 구조화된 데이터 반환

### 3. Google Calendar API 연동
- OAuth 2.0 인증 구현
- 캘린더 일정 추가 (events.insert)
- 오늘 일정 조회 (events.list)
- 사용자별 캘린더 접근 권한 관리

### 4. 자동 일정 알림
- 매일 오전 9시 (한국 시간 기준)에 실행
- 모든 등록된 사용자에게 오늘 일정 전송
- 일정이 없으면 "오늘은 예정된 일정이 없습니다" 메시지

## 프로젝트 구조

```
telegram-calendar-bot/
├── app/
│   ├── __init__.py
│   ├── main.py                 # 메인 실행 파일
│   ├── telegram_bot.py         # 텔레그램 봇 핸들러
│   ├── calendar_service.py     # 구글 캘린더 API 로직
│   ├── nlp_service.py          # Claude API를 이용한 자연어 처리
│   ├── scheduler.py            # APScheduler 설정 및 매일 알림
│   └── config.py               # 환경 변수 및 설정
├── data/
│   ├── credentials.json        # Google OAuth 클라이언트 시크릿
│   └── tokens/                 # 사용자별 토큰 저장 (volume mount)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## 환경 변수 (.env)

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Anthropic Claude API
ANTHROPIC_API_KEY=your_anthropic_api_key

# Google Calendar API
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=urn:ietf:wg:oauth:2.0:oob

# Shared Calendar (팀 공유 캘린더 ID)
# 구글 캘린더 설정 > 특정 캘린더 설정 > 캘린더 통합 > 캘린더 ID 복사
SHARED_CALENDAR_ID=your_shared_calendar_id@group.calendar.google.com

# Timezone
TIMEZONE=Asia/Seoul

# Scheduler
DAILY_REPORT_TIME=09:00
```

## 주요 구현 세부사항

### 1. telegram_bot.py
```python
# 구현해야 할 핸들러:
# - /start: 봇 시작 및 구글 인증 URL 제공
# - /auth <code>: OAuth 인증 코드 입력 및 토큰 저장
# - /today: 오늘 일정 수동 조회
# - 일반 텍스트 메시지: 자연어로 일정 추가
```

### 2. nlp_service.py
```python
# Claude API 호출 시 프롬프트 예시:
"""
다음 메시지에서 캘린더 일정 정보를 추출해주세요.
오늘 날짜: {today_date}

메시지: {user_message}

다음 JSON 형식으로만 응답해주세요:
{
  "title": "일정 제목",
  "date": "YYYY-MM-DD",
  "start_time": "HH:MM",
  "end_time": "HH:MM (선택)",
  "description": "설명 (선택)"
}

날짜가 상대적이면 (예: 내일, 다음주) 절대 날짜로 변환해주세요.
"""
```

### 3. calendar_service.py
```python
# 주요 메서드:
# - authenticate_user(chat_id, auth_code): OAuth 인증 및 토큰 저장
# - check_calendar_access(chat_id): 공유 캘린더 접근 권한 확인
# - add_event(chat_id, event_data): 공유 캘린더에 일정 추가
# - get_today_events(): 공유 캘린더의 오늘 일정 조회 (모든 팀원 공통)
# - is_authenticated(chat_id): 인증 상태 확인

# 중요: 모든 캘린더 작업은 SHARED_CALENDAR_ID를 사용
# calendar_id='primary' 대신 calendar_id=SHARED_CALENDAR_ID 사용
```

### 4. scheduler.py
```python
# APScheduler 사용:
# - CronTrigger로 매일 9시 실행
# - 공유 캘린더에서 오늘 일정 조회 (한 번만)
# - 모든 인증된 사용자에게 동일한 일정 목록 전송
# - 팀 전체가 같은 일정을 공유하므로 중복 조회 불필요
```

## Docker 구성

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY data/credentials.json ./data/

CMD ["python", "-m", "app.main"]
```

### docker-compose.yml
```yaml
version: '3.8'

services:
  telegram-bot:
    build: .
    env_file:
      - .env
    volumes:
      - ./data/tokens:/app/data/tokens
    restart: unless-stopped
    environment:
      - TZ=Asia/Seoul
```

## 보안 고려사항

1. **토큰 저장**: 사용자별 Google OAuth 토큰을 암호화하여 저장
2. **환경 변수**: API 키를 절대 코드에 하드코딩하지 않음
3. **Volume 권한**: Docker volume 권한 적절히 설정 (0600)
4. **에러 로깅**: 민감 정보가 로그에 노출되지 않도록 주의
5. **캘린더 권한 확인**: 
   - 사용자 인증 시 공유 캘린더 접근 권한 검증
   - 권한이 없으면 "공유 캘린더 접근 권한이 없습니다. 관리자에게 문의하세요" 메시지
   - 필요한 권한: `https://www.googleapis.com/auth/calendar`

## 구현 순서

1. **기본 텔레그램 봇 설정** - /start 명령어 응답
2. **Google OAuth 인증 플로우** - 사용자 인증 및 토큰 저장
3. **공유 캘린더 접근 확인** - 사용자가 공유 캘린더 권한이 있는지 검증
4. **Claude API 자연어 파싱** - 메시지에서 일정 정보 추출
5. **공유 캘린더 일정 추가** - SHARED_CALENDAR_ID에 일정 추가
6. **스케줄러 구현** - 매일 9시 팀 전체에 공유 일정 알림
7. **Docker 빌드 및 배포** - DigitalOcean에 배포

## 테스트 시나리오

### 자연어 입력 예시
- "내일 오후 2시에 치과 예약"
- "다음주 월요일 10시부터 11시까지 주간 회의"
- "3월 15일 저녁 7시에 저녁 약속 추가해줘"
- "오늘 오후 3시 프로젝트 리뷰"

### 예상 봇 응답
```
✅ 일정이 추가되었습니다!

📅 2024-03-15 (금)
🕐 19:00 - 20:00
📝 저녁 약속
```

## 추가 기능 (선택사항)

- `/list`: 이번 주 일정 조회
- `/delete <일정번호>`: 일정 삭제
- 일정 시작 30분 전 리마인더
- 다중 캘린더 지원 (업무/개인 구분)
- 반복 일정 추가 ("매주 월요일 10시 회의")

## 공유 캘린더 설정 가이드

### Google Calendar 공유 캘린더 ID 확인 방법

1. **구글 캘린더 웹 접속** (calendar.google.com)
2. **공유 캘린더 선택** (왼쪽 사이드바)
3. **캘린더 설정** (캘린더 이름 옆 ⋮ 클릭 → "설정 및 공유")
4. **"캘린더 통합" 섹션**에서 "캘린더 ID" 복사
   - 형식: `xxxxxxxxxxxxx@group.calendar.google.com`

### 팀원 권한 설정

공유 캘린더 설정에서 팀원들에게 다음 권한 부여:
- **"일정 변경" 권한** (필수): 봇이 일정을 추가할 수 있음
- 또는 **"일정 변경 및 공유 관리" 권한**: 전체 관리 가능

### 봇 동작 흐름

1. **팀원 A**: 자기 구글 계정으로 봇 인증 → 공유 캘린더 접근 권한 확인
2. **팀원 A**: "내일 오후 3시 회의" → 공유 캘린더에 추가
3. **팀원 B**: 자기 구글 계정으로 봇 인증 → 동일한 공유 캘린더 접근
4. **팀원 B**: "다음주 월요일 10시 브레인스토밍" → 같은 공유 캘린더에 추가
5. **매일 오전 9시**: 모든 팀원에게 공유 캘린더의 오늘 일정 전송

### 권한 없을 때 에러 처리

```
❌ 공유 캘린더에 접근할 수 없습니다.

캘린더 관리자에게 다음을 요청하세요:
1. 공유 캘린더 설정 열기
2. "특정 사용자와 공유" 섹션
3. 귀하의 이메일 추가 (your_email@gmail.com)
4. 권한: "일정 변경" 이상 부여
```

---

- [python-telegram-bot 문서](https://docs.python-telegram-bot.org/)
- [Google Calendar API](https://developers.google.com/calendar/api/guides/overview)
- [Anthropic Claude API](https://docs.anthropic.com/claude/reference/getting-started-with-the-api)
- [APScheduler 문서](https://apscheduler.readthedocs.io/)

## 구현 시 주의사항

1. **시간대 처리**: 모든 날짜/시간은 한국 시간(Asia/Seoul) 기준으로 처리
2. **에러 핸들링**: API 호출 실패, 인증 만료, 날짜 파싱 실패 등 예외 상황 대비
3. **Rate Limiting**: Google Calendar API 할당량 초과 방지
4. **토큰 갱신**: Google OAuth 토큰 만료 시 자동 갱신 로직
5. **로깅**: 디버깅을 위한 적절한 로그 레벨 설정

---

이 가이드를 Claude Code에게 전달하여 완전한 구현 코드를 요청하세요.