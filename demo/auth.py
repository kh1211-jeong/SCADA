# -*- coding: utf-8 -*-
"""외부 공개용 로그인: 비밀번호 2종(보기 전용 / 운영자) + 서명 쿠키. 추가 패키지 없음.

비밀번호 파일: ~/agents/demo-web/.env  (SCADA_AUTH_FILE로 경로 변경 가능, git에 올리지 않음)
    SCADA_VIEW_PW=...   보기 전용: 화면 보기, 이상 점수 추이, 진단 채팅 질문(사용량 제한 안에서)
    SCADA_OP_PW=...     운영자: 위 + 차단기 조작, 이벤트 주입, 배속·평상 복귀·자동 진단, 에이전트 연결/해제, 실시간 해설
    SCADA_SECRET=...    쿠키 서명 키
파일이 없으면 로그인 없이 동작한다(로컬 개발용). 외부 공개 전에는 반드시 파일을 만든다(make_auth_file).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

AUTH_FILE = Path(os.environ.get('SCADA_AUTH_FILE', Path.home() / 'agents' / 'demo-web' / '.env'))
COOKIE = 'scada_auth'
MAX_AGE = 12 * 3600
# 운영자만 쓸 수 있는 API (POST). 보기 전용 사용자가 부르면 403.
OP_ONLY = {'/api/switch', '/api/inject', '/api/control', '/api/agent', '/api/narrate'}
OPEN_PATHS = {'/login', '/logout', '/static/login.css'}


def _load():
    d = {}
    if AUTH_FILE.exists():
        for line in AUTH_FILE.read_text().splitlines():
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.split('=', 1); d[k.strip()] = v.strip()
    return d


CFG = _load()
ENABLED = bool(CFG.get('SCADA_VIEW_PW') and CFG.get('SCADA_OP_PW') and CFG.get('SCADA_SECRET'))
_fails: dict[str, list[float]] = {}


def make_auth_file():
    """비밀번호 파일 생성(없을 때만). 값은 화면에 출력하지 않는다 — 파일을 직접 열어 확인."""
    if AUTH_FILE.exists(): return False
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(f"SCADA_VIEW_PW={secrets.token_urlsafe(9)}\nSCADA_OP_PW={secrets.token_urlsafe(12)}\nSCADA_SECRET={secrets.token_hex(32)}\n")
    AUTH_FILE.chmod(0o600)
    return True


def _sign(role, exp):
    msg = f'{role}|{exp}'.encode()
    sig = hmac.new(CFG['SCADA_SECRET'].encode(), msg, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(msg).decode() + '.' + sig


def role_of(req):
    if not ENABLED: return 'op'
    tok = req.cookies.get(COOKIE, '')
    try:
        b, sig = tok.split('.', 1)
        msg = base64.urlsafe_b64decode(b.encode())
        good = hmac.new(CFG['SCADA_SECRET'].encode(), msg, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good): return None
        role, exp = msg.decode().split('|')
        return role if int(exp) > time.time() and role in ('view', 'op') else None
    except Exception:
        return None


LOGIN_HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>수배전 감시·진단 로그인</title><style>
body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;background:#000;color:#ececec;font:14px "Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif}
form{background:#0d0d0d;border:1px solid #2b2b2b;border-radius:12px;padding:26px 28px;width:320px}
h1{font-size:17px;margin:0 0 4px}p{color:#9a9a9a;margin:0 0 18px;font-size:12.5px}
input{width:100%;box-sizing:border-box;padding:10px;border-radius:8px;border:1px solid #2b2b2b;background:#171717;color:#fff;font-size:14px}
button{margin-top:12px;width:100%;padding:10px;border:0;border-radius:8px;background:#7aa8ff;color:#000;font-weight:700;font-size:14px;cursor:pointer}
.e{color:#ff8a8a;font-size:12.5px;margin-top:10px;min-height:16px}</style></head><body>
<form method="post" action="/login"><h1>⚡ 수배전 감시·진단 데모</h1><p>받은 비밀번호를 입력하세요. 보기 전용 / 운영자 비밀번호에 따라 권한이 정해집니다.</p>
<input type="password" name="pw" placeholder="비밀번호" autofocus autocomplete="current-password"><button>들어가기</button><div class="e">__ERR__</div></form></body></html>"""


async def login(req):
    if req.method == 'GET':
        return HTMLResponse(LOGIN_HTML.replace('__ERR__', ''))
    ip = req.headers.get('cf-connecting-ip') or (req.client.host if req.client else '?')
    now = time.time()
    f = [t for t in _fails.get(ip, []) if now - t < 600]
    if len(f) >= 8:
        return HTMLResponse(LOGIN_HTML.replace('__ERR__', '시도가 너무 많습니다. 10분 뒤 다시 시도하세요.'), status_code=429)
    pw = (await req.form()).get('pw', '')
    role = 'op' if hmac.compare_digest(pw, CFG['SCADA_OP_PW']) else 'view' if hmac.compare_digest(pw, CFG['SCADA_VIEW_PW']) else None
    if not role:
        _fails[ip] = f + [now]
        await asyncio.sleep(0.8)
        return HTMLResponse(LOGIN_HTML.replace('__ERR__', '비밀번호가 맞지 않습니다.'), status_code=401)
    _fails.pop(ip, None)
    r = RedirectResponse('/', status_code=303)
    https = req.url.scheme == 'https' or req.headers.get('x-forwarded-proto') == 'https'
    r.set_cookie(COOKIE, _sign(role, int(now) + MAX_AGE), max_age=MAX_AGE, httponly=True, samesite='lax', secure=https)
    return r


async def logout(_):
    r = RedirectResponse('/login', status_code=303); r.delete_cookie(COOKIE); return r


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, req, call_next):
        if not ENABLED or req.url.path in OPEN_PATHS:
            return await call_next(req)
        role = role_of(req)
        if role is None:
            if req.url.path.startswith('/api/'): return JSONResponse({'error': '로그인이 필요합니다'}, status_code=401)
            return RedirectResponse('/login', status_code=303)
        if role != 'op' and req.method == 'POST' and req.url.path in OP_ONLY:
            return JSONResponse({'error': '보기 전용 권한입니다 — 운영자 비밀번호로 로그인하세요'}, status_code=403)
        req.state.role = role
        return await call_next(req)
