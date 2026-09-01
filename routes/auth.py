"""
RKLLM NPU WebUI - 认证路由
登录、登出、修改密码、登录状态检查、登录验证码。
"""

import base64
import hashlib
import io
import random
import secrets
import sqlite3
import string
import time

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import DB_FILE
from database import (
    get_user_session_token, set_user_session_token,
    clear_user_session_token, verify_session_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    captcha_id: str = Field("", max_length=64)
    captcha: str = Field("", max_length=10)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


async def require_auth(request: Request):
    username = request.session.get("username")
    session_token = request.session.get("session_token")

    if not username or not session_token:
        raise HTTPException(status_code=401, detail="未登录")

    if not verify_session_token(username, session_token):
        raise HTTPException(status_code=401, detail="会话已失效，请重新登录")


# 简单的内存限流器：最多10次/60秒/IP
_login_attempts = {}


# ================= 登录验证码 =================
# 验证码存服务端内存（会话 cookie 可被客户端解码，不能存 session）
CAPTCHA_TTL = 300  # 5 分钟有效
CAPTCHA_MAX = 1000  # 内存中的验证码上限（防止恶意刷爆内存）
_captcha_store = {}  # captcha_id -> (code, expire_ts)

# 排除易混淆字符：0/O、1/I/L
CAPTCHA_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _gen_captcha_code(length=4):
    return "".join(random.choices(CAPTCHA_CHARS, k=length))


def _gen_captcha_image(code):
    """生成验证码图片，返回 data URI；无 PIL 时回退为 SVG（仅开发环境）"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        width, height = 120, 44
        img = Image.new("RGB", (width, height), (45, 50, 60))
        draw = ImageDraw.Draw(img)
        # 干扰线
        for _ in range(6):
            draw.line(
                [(random.randint(0, width), random.randint(0, height)),
                 (random.randint(0, width), random.randint(0, height))],
                fill=(90, 100, 125), width=1)
        # 噪点
        for _ in range(40):
            draw.point((random.randint(0, width), random.randint(0, height)),
                       fill=(random.randint(100, 160), random.randint(100, 160), random.randint(100, 160)))
        try:
            font = ImageFont.load_default(size=30)
        except TypeError:
            font = ImageFont.load_default()
        for i, ch in enumerate(code):
            color = (random.randint(140, 255), random.randint(140, 255), random.randint(140, 255))
            draw.text((12 + i * 24 + random.randint(0, 5), random.randint(2, 8)),
                      ch, font=font, fill=color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        # SVG 兜底（仅当未安装 Pillow 时使用；生产环境请安装 pillow）
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="44">'
            '<rect width="120" height="44" fill="#2d323c"/>'
        )
        for i, ch in enumerate(code):
            rot = random.randint(-18, 18)
            svg += (f'<text x="{18 + i * 24}" y="30" font-size="26" fill="#fff" '
                    f'transform="rotate({rot} {18 + i * 24} 30)">{ch}</text>')
        svg += "</svg>"
        return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def _cleanup_captchas():
    now = time.time()
    expired = [k for k, v in _captcha_store.items() if v[1] < now]
    for k in expired:
        del _captcha_store[k]


@router.get("/captcha")
async def get_captcha():
    """获取登录验证码：返回 {id, image}，服务端按 id 保存答案"""
    _cleanup_captchas()
    if len(_captcha_store) >= CAPTCHA_MAX:
        _captcha_store.clear()
    code = _gen_captcha_code()
    captcha_id = secrets.token_hex(8)
    _captcha_store[captcha_id] = (code, int(time.time()) + CAPTCHA_TTL)
    return {"id": captcha_id, "image": _gen_captcha_image(code)}


def _verify_captcha(captcha_id, captcha):
    """校验验证码（一次性），成功返回 None，失败返回错误信息"""
    if not captcha_id or captcha_id not in _captcha_store:
        return "验证码已过期，请刷新"
    code, expire = _captcha_store.pop(captcha_id, (None, 0))
    if code is None or int(time.time()) > expire:
        return "验证码已过期，请刷新"
    if captcha.strip().upper() != code:
        return "验证码错误"
    return None


@router.post("/login")
async def auth_login(req: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = 60  # 60秒窗口
    max_attempts = 10  # 最多10次

    # 清理过期记录
    _login_attempts.setdefault(client_ip, []).append(now)
    _login_attempts[client_ip] = [t for t in _login_attempts[client_ip] if now - t < window]

    if len(_login_attempts[client_ip]) > max_attempts:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    # 验证码校验（先于密码校验，防止绕过）
    captcha_err = _verify_captcha(req.captcha_id, req.captcha)
    if captcha_err:
        return JSONResponse(status_code=401,
                            content={"status": "error", "message": captcha_err})

    username = req.username.strip()
    password = req.password

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT password_hash, salt FROM users WHERE username = ?",
                  (username,))
        row = c.fetchone()
        if row:
            stored_hash, salt = row
            computed = hashlib.sha256((password + salt).encode()).hexdigest()
            if computed == stored_hash:
                token = set_user_session_token(username)
                request.session["authenticated"] = True
                request.session["username"] = username
                request.session["session_token"] = token
                return {"status": "success", "username": username}

    return JSONResponse(status_code=401,
                        content={"status": "error", "message": "用户名或密码错误"})


@router.post("/logout")
async def auth_logout(request: Request):
    username = request.session.get("username")
    if username:
        clear_user_session_token(username)
    request.session.clear()
    return {"status": "success"}


@router.post("/change-password", dependencies=[Depends(require_auth)])
async def change_password(req: ChangePasswordRequest, request: Request):
    old_password = req.old_password
    new_password = req.new_password

    if not new_password or len(new_password) < 8:
        return JSONResponse(status_code=400,
                            content={"status": "error", "message": "新密码至少需要8个字符"})
    has_letter = any(c.isalpha() for c in new_password)
    has_digit = any(c.isdigit() for c in new_password)
    if not (has_letter and has_digit):
        return JSONResponse(status_code=400,
                            content={"status": "error", "message": "新密码必须包含字母和数字"})

    username = request.session.get("username", "admin")
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT password_hash, salt FROM users WHERE username = ?",
                  (username,))
        row = c.fetchone()
        if row:
            stored_hash, salt = row
            computed = hashlib.sha256((old_password + salt).encode()).hexdigest()
            if computed == stored_hash:
                new_salt = secrets.token_hex(16)
                new_hash = hashlib.sha256(
                    (new_password + new_salt).encode()).hexdigest()
                c.execute(
                    "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
                    (new_hash, new_salt, username))
                conn.commit()
                clear_user_session_token(username)
                request.session.clear()
                return {"status": "success", "message": "密码修改成功，请重新登录"}

    return JSONResponse(status_code=401,
                        content={"status": "error", "message": "原密码错误"})


@router.get("/status")
async def auth_status(request: Request):
    username = request.session.get("username")
    session_token = request.session.get("session_token")
    if username and session_token and verify_session_token(username, session_token):
        return {"authenticated": True, "username": username}
    return {"authenticated": False}