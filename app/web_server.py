import logging

from aiohttp import web

from app import calendar_service
from app.config import OAUTH_SERVER_PORT

logger = logging.getLogger(__name__)

_bot_app = None  # telegram Application reference

SUCCESS_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>인증 완료</title>
<style>
body{display:flex;justify-content:center;align-items:center;height:100vh;margin:0;
font-family:-apple-system,sans-serif;background:#f0f2f5}
.card{text-align:center;background:#fff;padding:40px 60px;border-radius:16px;
box-shadow:0 2px 12px rgba(0,0,0,.1)}
h1{font-size:48px;margin:0}
p{color:#333;font-size:18px;margin-top:16px}
</style></head>
<body><div class="card"><h1>&#x2705;</h1>
<p>인증이 완료되었습니다!<br>텔레그램 앱으로 돌아가세요.</p></div></body></html>"""

ERROR_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>인증 실패</title>
<style>
body{display:flex;justify-content:center;align-items:center;height:100vh;margin:0;
font-family:-apple-system,sans-serif;background:#f0f2f5}
.card{text-align:center;background:#fff;padding:40px 60px;border-radius:16px;
box-shadow:0 2px 12px rgba(0,0,0,.1)}
h1{font-size:48px;margin:0}
p{color:#c00;font-size:18px;margin-top:16px}
</style></head>
<body><div class="card"><h1>&#x274C;</h1>
<p>%s</p></div></body></html>"""


async def oauth_callback(request: web.Request) -> web.Response:
    code = request.query.get("code")
    state = request.query.get("state")  # chat_id

    if not code or not state:
        return web.Response(
            text=ERROR_HTML % "인증 코드 또는 상태 정보가 없습니다.<br>다시 시도해주세요.",
            content_type="text/html",
        )

    try:
        chat_id = int(state)
    except ValueError:
        return web.Response(
            text=ERROR_HTML % "잘못된 인증 요청입니다.",
            content_type="text/html",
        )

    # Exchange code and authenticate
    success, message = await calendar_service.authenticate_user(chat_id, code)

    # Send result to Telegram
    if _bot_app is not None:
        try:
            if success:
                await _bot_app.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ 인증 성공!\n{message}\n\n"
                        "이제 자연어로 일정을 관리할 수 있습니다.\n"
                        '예: "내일 오후 3시에 팀 회의"'
                    ),
                )
            else:
                await _bot_app.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ 인증 실패\n{message}",
                )
        except Exception:
            logger.exception("Failed to send auth result to chat_id=%s", chat_id)

    if success:
        return web.Response(text=SUCCESS_HTML, content_type="text/html")
    else:
        return web.Response(
            text=ERROR_HTML % f"인증에 실패했습니다.<br>{message}",
            content_type="text/html",
        )


async def start_web_server(application) -> None:
    """Start the OAuth callback web server. Call from post_init."""
    global _bot_app
    _bot_app = application

    app = web.Application()
    app.router.add_get("/oauth/callback", oauth_callback)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", OAUTH_SERVER_PORT)
    await site.start()
    logger.info("OAuth callback server started on port %s", OAUTH_SERVER_PORT)
