"""
RKLLM NPU WebUI - 主入口
组装 FastAPI 应用、注册中间件、挂载静态文件、启动事件。
运行: python main.py
"""

import asyncio
import os
import secrets
import sys

# Windows 控制台默认 GBK，代码里含 emoji 的 print 会崩，统一切到 utf-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import SESSION_SECRET_FILE
from database import init_db, get_model_by_id
import npu

# ---- FastAPI 应用创建 ----
app = FastAPI(title="RKLLM Multi-Session WebUI with SQLite", docs_url=None, redoc_url=None, openapi_url=None)

# ---- 速率限制 ----
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---- 静态文件 (开发机回退到本地 static 目录) ----
STATIC_DIR = "/opt/rkllama/static"
if not os.path.isdir(STATIC_DIR):
    STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ---- Session 中间件 (登录认证) ----
if os.path.exists(SESSION_SECRET_FILE):
    with open(SESSION_SECRET_FILE, "rb") as f:
        SESSION_SECRET = f.read()
else:
    SESSION_SECRET = secrets.token_bytes(32)
    secret_path = SESSION_SECRET_FILE
    if os.name == "nt":
        secret_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".session_secret")
    with open(secret_path, "wb") as f:
        f.write(SESSION_SECRET)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="rkllm_session",
    max_age=86400,
)

# ---- 安全响应头中间件 ----
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    return response


# ---- 注册路由 ----
from routes.auth import router as auth_router
from routes.chat import router as chat_router
from routes.models import router as models_router
from routes.sessions import router as sessions_router
from routes.system_prompt import router as system_prompt_router
from routes.prompts import router as prompts_router
from routes.knowledge import router as knowledge_router
from routes.driver import router as driver_router
from frontend import router as frontend_router

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(models_router)
app.include_router(sessions_router)
app.include_router(system_prompt_router)
app.include_router(prompts_router)
app.include_router(knowledge_router)
app.include_router(driver_router)
app.include_router(frontend_router)


# ---- 启动事件 ----
@app.on_event("startup")
async def startup_event():
    init_db()
    # Only auto-start rkllm engine if default model uses it
    default_model = get_model_by_id(npu.current_model_id)
    if default_model and default_model.get("engine") == "rkllm":
        asyncio.create_task(npu.start_llm())
    else:
        print("[*] Default model uses non-rkllm engine, skipping auto-start")


# ---- 入口 ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
