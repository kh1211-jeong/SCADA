# -*- coding: utf-8 -*-
"""외부 공개용 로그인: 계정 2종(관리자 admin / 사용자 user) + 서명 쿠키. 추가 패키지 없음.

계정 파일: ~/agents/demo-web/.env  (SCADA_AUTH_FILE로 경로 변경 가능, git에 올리지 않음)
    SCADA_ADMIN_PW=...  admin 계정: 모든 기능
    SCADA_USER_PW=...   user 계정: 차단기 조작·트립 모의·이벤트 주입·질문·해설 가능, **에이전트 연결/해제·호출 경로 변경만 불가**
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
ADMIN_ONLY = {'/api/agent'}   # POST(연결/해제·경로 변경). GET(연결 정보 보기)은 모두 가능
OPEN_PATHS = {'/login', '/logout', '/static/login.css'}


def _load():
    d = {}
    if AUTH_FILE.exists():
        for line in AUTH_FILE.read_text().splitlines():
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.split('=', 1); d[k.strip()] = v.strip()
    return d


CFG = _load()
ENABLED = bool(CFG.get('SCADA_ADMIN_PW') and CFG.get('SCADA_USER_PW') and CFG.get('SCADA_SECRET'))
ACCOUNTS = {'admin': ('SCADA_ADMIN_PW', 'admin'), 'user': ('SCADA_USER_PW', 'user')}   # 아이디 -> (비밀번호 키, 역할)
_fails: dict[str, list[float]] = {}


def make_auth_file():
    """비밀번호 파일 생성(없을 때만). 값은 화면에 출력하지 않는다 — 파일을 직접 열어 확인."""
    if AUTH_FILE.exists(): return False
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(f"SCADA_ADMIN_PW={secrets.token_urlsafe(12)}\nSCADA_USER_PW={secrets.token_urlsafe(9)}\nSCADA_SECRET={secrets.token_hex(32)}\n")
    AUTH_FILE.chmod(0o600)
    return True


def _sign(role, exp):
    msg = f'{role}|{exp}'.encode()
    sig = hmac.new(CFG['SCADA_SECRET'].encode(), msg, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(msg).decode() + '.' + sig


def role_of(req):
    if not ENABLED: return 'admin'
    tok = req.cookies.get(COOKIE, '')
    try:
        b, sig = tok.split('.', 1)
        msg = base64.urlsafe_b64decode(b.encode())
        good = hmac.new(CFG['SCADA_SECRET'].encode(), msg, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good): return None
        role, exp = msg.decode().split('|')
        return role if int(exp) > time.time() and role in ('admin', 'user') else None
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
<form method="post" action="/login"><h1>⚡ 수배전 감시·진단 데모</h1><p>아이디와 비밀번호를 입력하세요.</p>
<input name="id" placeholder="아이디" autofocus autocomplete="username" style="margin-bottom:8px">
<input type="password" name="pw" placeholder="비밀번호" autocomplete="current-password"><button>들어가기</button><div class="e">__ERR__</div></form></body></html>"""


async def login(req):
    if req.method == 'GET':
        return HTMLResponse(LOGIN_HTML.replace('__ERR__', ''))
    ip = req.headers.get('cf-connecting-ip') or (req.client.host if req.client else '?')
    now = time.time()
    f = [t for t in _fails.get(ip, []) if now - t < 600]
    if len(f) >= 8:
        return HTMLResponse(LOGIN_HTML.replace('__ERR__', '시도가 너무 많습니다. 10분 뒤 다시 시도하세요.'), status_code=429)
    form = await req.form()
    uid, pw = str(form.get('id', '')).strip().lower(), str(form.get('pw', ''))
    acc = ACCOUNTS.get(uid)
    role = acc[1] if acc and hmac.compare_digest(pw.encode(), CFG[acc[0]].encode()) else None
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
        if role != 'admin' and req.method == 'POST' and req.url.path in ADMIN_ONLY:
            return JSONResponse({'error': '에이전트 연결/해제는 관리자(admin)만 할 수 있습니다'}, status_code=403)
        req.state.role = role
        return await call_next(req)
