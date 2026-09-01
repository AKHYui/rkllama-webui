"""
RKLLM NPU WebUI - 认证路由
登录、登出、修改密码、登录状态检查。
"""

import hashlib
import secrets
import sqlite3

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import DB_FILE
from database import (
    get_user_session_token, set_user_session_token,
    clear_user_session_token, verify_session_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


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


# 简单的内存限流器：最多5次/60秒/IP
_login_attempts = {}

@router.post("/login")
async def auth_login(req: LoginRequest, request: Request):
    import time
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = 60  # 60秒窗口
    max_attempts = 10  # 最多10次

    # 清理过期记录
    _login_attempts.setdefault(client_ip, []).append(now)
    _login_attempts[client_ip] = [t for t in _login_attempts[client_ip] if now - t < window]

    if len(_login_attempts[client_ip]) > max_attempts:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
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
