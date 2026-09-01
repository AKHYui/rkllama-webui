import asyncio
import json
import os
import sqlite3
import uuid
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from typing import List, Optional
import hashlib
import secrets

# ================= 核心配置区 =================
MODELS = [
    {
        "id": "qwen3.5-4b-abliterated-16k",
        "name": "Qwen3.5 4B Abliterated 16K",
        "path": "/opt/models/Qwen3.5-4B-abliterated/Qwen3.5-4B-abliterated_RK3588_w8a8_ctx16384.rkllm",
        "ctx_max": 16384
    },
    {
        "id": "qwen3-4b-abliterated-16k",
        "name": "Qwen3 4B Abliterated 16K",
        "path": "/opt/models/Qwen3-4B-abliterated/Qwen3-4B-abliterated-w8a8-rk3588-16k.rkllm",
        "ctx_max": 16384
    },
    {
        "id": "gemma4-e2b",
        "name": "Gemma4 E2B",
        "path": "/opt/models/Gemma-4-E2B-it/gemma-4-E2B-it_RK3588_w8a8.rkllm",
        "ctx_max": 4096
    },
    {
        "id": "qwen3-4b",
        "name": "Qwen3 4B",
        "path": "/opt/models/Qwen3-4B/Qwen3-4B-rk3588-w8a8-opt-1-hybrid-ratio-1.0.rkllm"
    },
    {
        "id": "qwen3-1.7b",
        "name": "Qwen3 1.7B",
        "path": "/opt/models/Qwen3-1.7B/Qwen3-1.7B-w8a8-rk3588.rkllm"
    },
    {
        "id": "Qwen2.5-0.5b",
        "name": "Qwen2.5 0.5B",
        "path": "/opt/models/Qwen2.5-0.5B/Qwen2.5-0.5B-Instruct-1.2.0.rkllm"
    },
    {
        "id": "Deepseek-1.5b",
        "name": "Deepseek 1.5B",
        "path": "/opt/models/Deepseek-R1-1.5b/DeepSeek-R1-Distill-Qwen-1.5B-rk3588-w8a8-opt-1-hybrid-ratio-0.0.rkllm"
    }
]

# ========== 新增：默认系统提示词 ==========
DEFAULT_SYSTEM_PROMPT = """你是一个有帮助的AI助手。请直接、简洁地回答用户的问题。"""

# ================= 采样参数配置 =================
# 修改这些值后会自动重启 NPU 进程生效
SAMPLING_PARAMS = {
    "temperature": 0.8,      # 0.0-2.0, 越高越随机, 0=贪心解码
    "top_p": 0.95,           # 0.0-1.0, nucleus sampling 阈值
    "top_k": 40,             # 1-100, 采样候选数, 1=贪心解码
    "repeat_penalty": 1.1    # 1.0-2.0, 重复惩罚, 越高越不容易重复
}
# ==============================================

PROMPT_SIGN = "user:" 
DB_FILE = "chat_history.db"
# ==============================================

app = FastAPI(title="RKLLM Multi-Session WebUI with SQLite")
app.mount("/static", StaticFiles(directory="/opt/rkllama/static"), name="static")

# ================= 登录认证配置 =================
SESSION_SECRET_FILE = "/opt/rkllama/.session_secret"
if os.path.exists(SESSION_SECRET_FILE):
    with open(SESSION_SECRET_FILE, "rb") as f:
        SESSION_SECRET = f.read()
else:
    SESSION_SECRET = secrets.token_bytes(32)
    with open(SESSION_SECRET_FILE, "wb") as f:
        f.write(SESSION_SECRET)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, session_cookie="rkllm_session", max_age=86400)
# ==============================================

llm_process = None
llm_lock = asyncio.Lock()

# 状态机管理
current_model_id = MODELS[0]["id"]
active_session_id = None

# ========== 新增：缓存当前系统提示词 ==========
current_system_prompt = DEFAULT_SYSTEM_PROMPT

def init_db():
    """初始化 SQLite 数据库"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        # 原有表
        c.execute('''CREATE TABLE IF NOT EXISTS sessions
                     (id TEXT PRIMARY KEY, title TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS messages
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT, content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # ========== 新增：系统提示词表 ==========
        c.execute('''CREATE TABLE IF NOT EXISTS system_prompts
                     (id INTEGER PRIMARY KEY CHECK (id = 1), 
                      content TEXT NOT NULL,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # 初始化默认系统提示词（如果不存在）
        c.execute("SELECT COUNT(*) FROM system_prompts")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO system_prompts (id, content) VALUES (1, ?)", 
                     (DEFAULT_SYSTEM_PROMPT,))
        
        # ========== 新增：用户认证表 ==========
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY CHECK (id = 1),
                      username TEXT NOT NULL UNIQUE,
                      password_hash TEXT NOT NULL,
                      salt TEXT NOT NULL)''')
        
        # 初始化默认管理员账号（如果不存在）
        c.execute("SELECT COUNT(*) FROM users")
        if c.fetchone()[0] == 0:
            salt = secrets.token_hex(16)
            default_password = "admin123"
            password_hash = hashlib.sha256((default_password + salt).encode()).hexdigest()
            c.execute("INSERT INTO users (id, username, password_hash, salt) VALUES (1, ?, ?, ?)",
                     ("admin", password_hash, salt))
        
        conn.commit()
    print("[💾] SQLite 数据库初始化完成")

def get_current_model_path():
    for m in MODELS:
        if m["id"] == current_model_id:
            return m["path"]
    return MODELS[0]["path"]


def get_current_model_ctx_max():
    for m in MODELS:
        if m["id"] == current_model_id:
            return m.get("ctx_max", 4096)
    return MODELS[0].get("ctx_max", 4096)

def get_system_prompt():
    """获取当前系统提示词"""
    global current_system_prompt
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT content FROM system_prompts WHERE id = 1")
            row = c.fetchone()
            if row:
                current_system_prompt = row[0]
    except:
        pass
    return current_system_prompt

async def kill_llm():
    global llm_process, active_session_id
    if llm_process is not None:
        try:
            llm_process.kill()
            await llm_process.wait()
            print("\n[♻️] 已彻底杀死旧 NPU 进程，物理内存已释放。")
        except Exception as e:
            print(f"\n[!] 释放进程失败: {e}")
        llm_process = None
        active_session_id = None

async def start_llm():
    global llm_process, active_session_id
    await kill_llm()
    
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = "/usr/local/lib/rkllm:" + env.get("LD_LIBRARY_PATH", "")
    model_path = get_current_model_path()
    
    print(f"\n[*] 正在为您拉起专属 NPU 引擎 (模型: {current_model_id})...")
    
    # 获取采样参数
    sp = SAMPLING_PARAMS
    llm_process = await asyncio.create_subprocess_exec(
        "llm_demo", model_path, "1024", str(get_current_model_ctx_max()),
        str(sp.get("temperature", 0.8)),
        str(sp.get("top_p", 0.95)),
        str(sp.get("top_k", 40)),
        str(sp.get("repeat_penalty", 1.1)),
        stdin=asyncio.subprocess.PIPE, 
        stdout=asyncio.subprocess.PIPE, 
        stderr=asyncio.subprocess.STDOUT, 
        env=env
    )
    
    byte_buffer = b""
    full_log = ""
    while True:
        try:
            char_byte = await llm_process.stdout.read(1)
            if not char_byte: return False
            byte_buffer += char_byte
            try:
                text = byte_buffer.decode('utf-8')
                print(text, end='', flush=True)
                full_log += text
                byte_buffer = b""
                if full_log.endswith(PROMPT_SIGN):
                    print(f"\n[*] 引擎已就绪！可以开始对话。")
                    return True
            except UnicodeDecodeError: continue
        except Exception as e:
            print(f"启动读取日志异常: {e}")
            return False


async def require_auth(request: Request):
    """验证用户是否已登录"""
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="未登录")

@app.on_event("startup")
async def startup_event():
    init_db()
    asyncio.create_task(start_llm())

# ========== 认证 API ==========
@app.post("/api/auth/login")
async def auth_login(request: Request):
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT password_hash, salt FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        if row:
            stored_hash, salt = row
            computed = hashlib.sha256((password + salt).encode()).hexdigest()
            if computed == stored_hash:
                request.session["authenticated"] = True
                request.session["username"] = username
                return {"status": "success", "username": username}
    
    return JSONResponse(status_code=401, content={"status": "error", "message": "用户名或密码错误"})

@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    request.session.clear()
    return {"status": "success"}

@app.post("/api/auth/change-password", dependencies=[Depends(require_auth)])
async def change_password(request: Request):
    body = await request.json()
    old_password = body.get("old_password", "")
    new_password = body.get("new_password", "")
    
    if not new_password or len(new_password) < 4:
        return JSONResponse(status_code=400, content={"status": "error", "message": "新密码至少需要4个字符"})
    
    username = request.session.get("username", "admin")
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT password_hash, salt FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        if row:
            stored_hash, salt = row
            computed = hashlib.sha256((old_password + salt).encode()).hexdigest()
            if computed == stored_hash:
                new_salt = secrets.token_hex(16)
                new_hash = hashlib.sha256((new_password + new_salt).encode()).hexdigest()
                c.execute("UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
                         (new_hash, new_salt, username))
                conn.commit()
                return {"status": "success", "message": "密码修改成功"}
    
    return JSONResponse(status_code=401, content={"status": "error", "message": "原密码错误"})

@app.get("/api/auth/status")
async def auth_status(request: Request):
    if request.session.get("authenticated"):
        return {"authenticated": True, "username": request.session.get("username", "")}
    return {"authenticated": False}

# ========== API 路由及模型 ==========
class SessionCreate(BaseModel):
    title: str = "新的聊天"

class ChatRequest(BaseModel):
    session_id: str
    query: str = ""
    regenerate: bool = False

class SwitchModelRequest(BaseModel):
    model_id: str

class SamplingUpdateRequest(BaseModel):
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    repeat_penalty: Optional[float] = None

# ========== 新增：系统提示词请求模型 ==========
class SystemPromptRequest(BaseModel):
    content: str

@app.get("/api/models", dependencies=[Depends(require_auth)])
async def get_models():
    return {"models": MODELS, "current": current_model_id}

@app.post("/api/switch", dependencies=[Depends(require_auth)])
async def switch_model_endpoint(req: SwitchModelRequest):
    global current_model_id
    if any(m["id"] == req.model_id for m in MODELS):
        current_model_id = req.model_id
        success = await start_llm()
        if success:
            return {"status": "success", "message": f"成功切换至 {req.model_id}"}
        return {"status": "error", "message": "模型拉起失败，请检查路径或显存占用"}
    return {"status": "error", "message": "未找到指定模型"}

@app.get("/api/sampling", dependencies=[Depends(require_auth)])
async def get_sampling_params():
    return {"params": SAMPLING_PARAMS, "description": {
        "temperature": "0.0-2.0, 越高越随机", 
        "top_p": "0.0-1.0, nucleus sampling",
        "top_k": "1-100, 候选token数", 
        "repeat_penalty": "1.0-2.0, 重复惩罚"
    }}

@app.post("/api/sampling", dependencies=[Depends(require_auth)])
async def update_sampling_params(req: SamplingUpdateRequest):
    """更新采样参数并自动重启 NPU 进程"""
    if req.temperature is not None:
        SAMPLING_PARAMS["temperature"] = req.temperature
    if req.top_p is not None:
        SAMPLING_PARAMS["top_p"] = req.top_p
    if req.top_k is not None:
        SAMPLING_PARAMS["top_k"] = req.top_k
    if req.repeat_penalty is not None:
        SAMPLING_PARAMS["repeat_penalty"] = req.repeat_penalty
    
    success = await start_llm()
    if success:
        return {"status": "success", "params": SAMPLING_PARAMS}
    return {"status": "error", "message": "NPU 重启失败"}

@app.post("/api/reset", dependencies=[Depends(require_auth)])
async def reset_chat():
    await start_llm()
    return {"status": "success", "message": "NPU 进程已重置，内存已清空"}

# ========== 新增：系统提示词 API ==========
@app.get("/api/system-prompt", dependencies=[Depends(require_auth)])
def get_system_prompt_api():
    """获取当前系统提示词"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT content FROM system_prompts WHERE id = 1")
        row = c.fetchone()
        content = row[0] if row else DEFAULT_SYSTEM_PROMPT
    return {"content": content}

@app.post("/api/system-prompt", dependencies=[Depends(require_auth)])
def save_system_prompt(req: SystemPromptRequest):
    """保存系统提示词"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO system_prompts (id, content, updated_at) 
                     VALUES (1, ?, CURRENT_TIMESTAMP)""", (req.content,))
        conn.commit()
    return {"status": "success", "message": "系统提示词已保存"}

# --- DB API ---
@app.get("/api/sessions", dependencies=[Depends(require_auth)])
def get_sessions():
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM sessions ORDER BY updated_at DESC")
        return [dict(row) for row in c.fetchall()]

@app.post("/api/sessions", dependencies=[Depends(require_auth)])
def create_session(req: SessionCreate):
    session_id = str(uuid.uuid4())[:8]
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO sessions (id, title) VALUES (?, ?)", (session_id, req.title))
        conn.commit()
    return {"id": session_id, "title": req.title}

@app.delete("/api/sessions/{session_id}", dependencies=[Depends(require_auth)])
def delete_session(session_id: str):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.commit()
    return {"status": "success"}

@app.get("/api/sessions/{session_id}/messages", dependencies=[Depends(require_auth)])
def get_messages(session_id: str):
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,))
        return [dict(row) for row in c.fetchall()]

# --- Chat API ---
@app.post("/api/chat", dependencies=[Depends(require_auth)])
async def chat_endpoint(request: ChatRequest):
    global active_session_id
    
    # ========== 新增：获取当前系统提示词 ==========
    system_prompt = get_system_prompt()
    
    if request.regenerate:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT id, role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 1", (request.session_id,))
            last_msg = c.fetchone()
            if last_msg and last_msg[1] == 'assistant':
                c.execute("DELETE FROM messages WHERE id = ?", (last_msg[0],))
                conn.commit()
            
            c.execute("SELECT content FROM messages WHERE session_id = ? AND role = 'user' ORDER BY id DESC LIMIT 1", (request.session_id,))
            user_msg = c.fetchone()
            clean_query = user_msg[0] if user_msg else ""
    else:
        clean_query = request.query.replace("\n", " ").replace("\r", " ").strip()
        
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", (request.session_id, 'user', clean_query))
            
            c.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (request.session_id,))
            msg_count = c.fetchone()[0]
            if msg_count == 1:
                new_title = clean_query[:15] + ('...' if len(clean_query) > 15 else '')
                c.execute("UPDATE sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_title, request.session_id))
            else:
                c.execute("UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (request.session_id,))
            conn.commit()

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 6", (request.session_id,))
        recent_history_raw = list(reversed([dict(row) for row in c.fetchall()]))
        
        history_for_prompt = []
        if recent_history_raw and recent_history_raw[-1]['role'] == 'user' and recent_history_raw[-1]['content'] == clean_query:
            history_for_prompt = recent_history_raw[:-1]
        else:
            history_for_prompt = recent_history_raw
    
    async def generate():
        global active_session_id
        async with llm_lock:
            try:
                if not llm_process or llm_process.returncode is not None:
                    raise RuntimeError("NPU Process dead")
                
                actual_query = clean_query
                
                if request.session_id != active_session_id:
                    print(f"\n[🔄] 检测到会话切换: {active_session_id} -> {request.session_id}，正在重置 NPU...")
                    await start_llm()
                    active_session_id = request.session_id
                    
                # ========== 核心修改：拼接系统提示词 + 历史 + 当前问题 ==========
                if history_for_prompt:
                    context_str = "【系统设定】" + system_prompt + "【请参考以下历史对话上下文】"
                    for msg in history_for_prompt:
                        role_name = "User" if msg['role'] == 'user' else "AI"
                        safe_content = msg['content'].replace('\n', ' ').replace('\r', ' ')
                        if len(safe_content) > 1500:
                            safe_content = safe_content[:1500] + " ... [内容已省略]"
                        context_str += f" {role_name}: {safe_content} |"
                    context_str += f" 【结合上述历史上下文和系统设定，请直接回答我的最新问题】 User: {clean_query} AI:"
                    actual_query = context_str
                    print(f"\n[🧠] 上下文重组完成 (含系统提示词)，总长: {len(actual_query)} 字符")
                else:
                    # 无历史时，也带入系统提示词
                    context_str = "【系统设定】" + system_prompt + f" User: {clean_query} AI:"
                    actual_query = context_str
                    print(f"\n[🧠] 无历史，使用系统提示词，总长: {len(actual_query)} 字符")
                
                llm_process.stdin.write((actual_query + "\n").encode('utf-8'))
                await llm_process.stdin.drain()
                
            except Exception as e:
                print(f"进程写入错误: {e}")
                yield f"data: {json.dumps({'content': '⚠️ NPU 进程未就绪或已崩溃，系统正在自动重启引擎...'}, ensure_ascii=False)}\n\n"
                await start_llm()
                return

            byte_buffer = b""
            full_response_text = ""
            chunk_buffer = ""
            is_first_chunk = True
            
            while True:
                try:
                    char = await llm_process.stdout.read(1)
                    if not char: break
                    
                    byte_buffer += char
                    try:
                        text_chunk = byte_buffer.decode('utf-8')
                        byte_buffer = b""
                        full_response_text += text_chunk
                        
                        if full_response_text.endswith(PROMPT_SIGN):
                            yield "data: [DONE]\n\n"
                            break
                        
                        if is_first_chunk:
                            if "robot:" in full_response_text:
                                text_chunk = full_response_text.split("robot:")[-1].lstrip()
                                is_first_chunk = False
                            elif len(full_response_text) > 15:
                                is_first_chunk = False
                            else:
                                continue 
                        
                        if not text_chunk and is_first_chunk: continue
                        
                        chunk_buffer += text_chunk
                        if chunk_buffer:
                            safe_to_send = chunk_buffer
                            for i in range(1, len(PROMPT_SIGN) + 1):
                                if chunk_buffer.endswith(PROMPT_SIGN[:i]):
                                    safe_to_send = chunk_buffer[:-i]
                                    break
                            
                            if safe_to_send:
                                yield f"data: {json.dumps({'content': safe_to_send}, ensure_ascii=False)}\n\n"
                                chunk_buffer = chunk_buffer[len(safe_to_send):]
                                
                    except UnicodeDecodeError: continue
                except Exception as e:
                    print(f"读取输出异常: {e}")
                    break

            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", (request.session_id, 'assistant', full_response_text))
                conn.commit()

    return StreamingResponse(generate(), media_type="text/event-stream")

# ================= 前端网页代码（增加系统提示词弹窗） =================
@app.get("/")
async def get_ui():
    html_content = r"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
        <title>RKLLM Multi-Session Chat</title>
        <script src="/static/tailwind.min.js"></script>
        <script src="/static/marked.min.js"></script>
        <link rel="stylesheet" href="/static/github-dark.min.css">
        <script src="/static/highlight.min.js"></script>
        <link rel="stylesheet" href="/static/katex.min.css">
        <script src="/static/katex.min.js"></script>
        <script src="/static/auto-render.min.js"></script>
        <style>
            html, body { height: 100%; height: 100dvh; }
            @supports (-webkit-touch-callout: none) { body { height: -webkit-fill-available; } }
            ::-webkit-scrollbar { width: 6px; }
            ::-webkit-scrollbar-track { background: transparent; }
            ::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
            ::-webkit-scrollbar-thumb:hover { background: #6b7280; }
            .prose pre { padding: 0; background-color: transparent; margin: 0; }
            .prose code { background-color: #374151; padding: 0.1rem 0.3rem; border-radius: 0.25rem; font-size: 0.85em; }
            .prose pre code { padding: 0.8rem; display: block; overflow-x: auto; font-size: 0.85em; line-height: 1.4; }
            .safe-area-bottom { padding-bottom: max(0.75rem, env(safe-area-inset-bottom)); }
            .sidebar-transition { transition: transform 0.3s ease-in-out; }
            /* 系统提示词弹窗样式 */
            .modal-overlay { transition: opacity 0.2s ease-in-out; }
            .modal-content { transition: transform 0.2s ease-in-out, opacity 0.2s ease-in-out; }
            .modal-hidden { opacity: 0; pointer-events: none; }
            .modal-hidden .modal-content { transform: scale(0.95); opacity: 0; }
        </style>
    </head>
    <body class="bg-gray-900 text-gray-100 h-full overflow-hidden flex font-sans">
        
        <!-- 登录遮罩层 -->
        <div id="loginOverlay" class="fixed inset-0 bg-gray-900 z-50 flex items-center justify-center">
            <div class="bg-gray-800 rounded-2xl shadow-2xl w-full max-w-sm p-8 border border-gray-700">
                <div class="text-center mb-6">
                    <svg class="w-12 h-12 mx-auto text-blue-500 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                    <h2 class="text-xl font-bold text-white">RKLLM NPU WebUI</h2>
                    <p class="text-sm text-gray-400 mt-1">请输入密码登录</p>
                </div>
                <div class="space-y-4">
                    <input id="loginUsername" type="text" placeholder="用户名" value="admin"
                        class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <input id="loginPassword" type="password" placeholder="密码"
                        class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        onkeydown="if(event.key==='Enter')doLogin()">
                    <p id="loginError" class="text-red-400 text-sm text-center hidden"></p>
                    <button onclick="doLogin()" id="loginBtn"
                        class="w-full bg-blue-600 hover:bg-blue-700 text-white rounded-lg py-3 font-medium transition-colors">
                        登 录
                    </button>
                </div>
            </div>
        </div>

        <!-- 修改密码弹窗 -->
        <div id="changePwdModal" class="modal-overlay fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 modal-hidden">
            <div class="modal-content bg-gray-800 rounded-2xl shadow-2xl w-full max-w-sm border border-gray-700">
                <div class="flex justify-between items-center p-4 border-b border-gray-700">
                    <h3 class="text-lg font-bold text-white">修改密码</h3>
                    <button onclick="closeChangePasswordModal()" class="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-700 transition-colors">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                    </button>
                </div>
                <div class="p-4 space-y-4">
                    <div>
                        <label class="text-xs text-gray-400 mb-1 block">原密码</label>
                        <input id="oldPassword" type="password" placeholder="输入当前密码"
                            class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500">
                    </div>
                    <div>
                        <label class="text-xs text-gray-400 mb-1 block">新密码</label>
                        <input id="newPassword" type="password" placeholder="至少4个字符"
                            class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500">
                    </div>
                    <div>
                        <label class="text-xs text-gray-400 mb-1 block">确认新密码</label>
                        <input id="confirmPassword" type="password" placeholder="再次输入新密码"
                            class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            onkeydown="if(event.key==='Enter')doChangePassword()">
                    </div>
                    <p id="changePwdError" class="text-red-400 text-sm text-center hidden"></p>
                    <p id="changePwdSuccess" class="text-green-400 text-sm text-center hidden"></p>
                    <div class="flex gap-3">
                        <button onclick="closeChangePasswordModal()"
                            class="flex-1 px-4 py-2.5 text-gray-300 hover:text-white hover:bg-gray-700 rounded-lg transition-colors text-sm border border-gray-600">
                            取消
                        </button>
                        <button onclick="doChangePassword()" id="changePwdBtn"
                            class="flex-1 px-4 py-2.5 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition-colors text-sm font-medium">
                            确认修改
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <!-- 系统提示词弹窗 -->
        <div id="systemPromptModal" class="modal-overlay fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 modal-hidden">
            <div class="modal-content bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col border border-gray-700">
                <!-- 弹窗头部 -->
                <div class="flex justify-between items-center p-4 border-b border-gray-700">
                    <div>
                        <h3 class="text-lg font-bold text-white">💡 系统提示词设置</h3>
                        <p class="text-xs text-gray-400 mt-1">设置 AI 助手的角色和行为规则，会自动带入每次对话</p>
                    </div>
                    <button onclick="closeSystemPromptModal()" class="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-700 transition-colors">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                    </button>
                </div>
                
                <!-- 预设快捷按钮 -->
                <div class="px-4 pt-3 pb-1 flex flex-wrap gap-2">
                    <span class="text-xs text-gray-400 mr-1 self-center">快速预设:</span>
                    <button onclick="setPresetPrompt('helpful')" class="text-xs px-2 py-1 bg-blue-600/30 hover:bg-blue-600/50 text-blue-300 rounded-full border border-blue-500/30 transition-colors">🤖 助手</button>
                    <button onclick="setPresetPrompt('coder')" class="text-xs px-2 py-1 bg-green-600/30 hover:bg-green-600/50 text-green-300 rounded-full border border-green-500/30 transition-colors">💻 程序员</button>
                    <button onclick="setPresetPrompt('teacher')" class="text-xs px-2 py-1 bg-purple-600/30 hover:bg-purple-600/50 text-purple-300 rounded-full border border-purple-500/30 transition-colors">📚 教师</button>
                    <button onclick="setPresetPrompt('translator')" class="text-xs px-2 py-1 bg-yellow-600/30 hover:bg-yellow-600/50 text-yellow-300 rounded-full border border-yellow-500/30 transition-colors">🌐 翻译官</button>
                    <button onclick="setPresetPrompt('expert')" class="text-xs px-2 py-1 bg-red-600/30 hover:bg-red-600/50 text-red-300 rounded-full border border-red-500/30 transition-colors">🧠 专业顾问</button>
                    <button onclick="clearPrompt()" class="text-xs px-2 py-1 bg-gray-600/30 hover:bg-gray-600/50 text-gray-300 rounded-full border border-gray-500/30 transition-colors">🗑️ 清空</button>
                </div>
                
                <!-- 文本编辑区 -->
                <div class="flex-1 p-4 min-h-0">
                    <textarea id="systemPromptInput" 
                        class="w-full h-48 bg-gray-900 border border-gray-600 rounded-xl p-3 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                        placeholder="输入系统提示词，例如：你是一个专业的中文写作助手，擅长润色文章、纠正语法错误..."
                        oninput="updatePromptCount()"></textarea>
                    <div class="flex justify-between items-center mt-2">
                        <span id="promptCount" class="text-xs text-gray-500">0 / 2000 字符</span>
                        <span class="text-xs text-gray-500">建议简洁明了，过长可能影响对话质量</span>
                    </div>
                </div>
                
                <!-- 弹窗底部按钮 -->
                <div class="flex justify-end gap-3 p-4 border-t border-gray-700">
                    <button onclick="closeSystemPromptModal()" 
                        class="px-4 py-2 text-gray-300 hover:text-white hover:bg-gray-700 rounded-lg transition-colors text-sm">
                        取消
                    </button>
                    <button onclick="saveSystemPrompt()" 
                        class="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors text-sm font-medium shadow-sm">
                        ✅ 保存提示词
                    </button>
                </div>
            </div>
        </div>

        <!-- 移动端侧边栏遮罩 -->
        <div id="mobileOverlay" class="fixed inset-0 bg-black/50 z-20 hidden md:hidden" onclick="toggleSidebar()"></div>
        
        <!-- 左侧会话侧边栏 -->
        <aside id="sidebar" class="fixed md:static inset-y-0 left-0 w-64 bg-gray-800 border-r border-gray-700 flex flex-col z-30 transform -translate-x-full md:translate-x-0 sidebar-transition shrink-0">
            <div class="p-4 border-b border-gray-700 flex justify-between items-center">
                <h2 class="text-lg font-bold text-gray-200">所有对话</h2>
                <button onclick="toggleSidebar()" class="md:hidden text-gray-400 hover:text-white">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            <div class="p-3">
                <button onclick="createNewSession()" class="w-full flex items-center justify-center space-x-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg py-2.5 transition-colors shadow-sm">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                    <span>新建聊天</span>
                </button>
            </div>
            <div id="sessionList" class="flex-1 overflow-y-auto p-2 space-y-1"></div>
        </aside>

        <!-- 右侧主聊天区域 -->
        <div class="flex-1 flex flex-col min-w-0 h-full relative">
            <header class="bg-gray-800 border-b border-gray-700 p-3 sm:p-4 flex justify-between items-center shadow-md z-10 shrink-0">
                <div class="flex items-center space-x-2 sm:space-x-3">
                    <button onclick="toggleSidebar()" class="md:hidden text-gray-400 hover:text-white mr-1">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
                    </button>
                    <div id="statusDot" class="w-3 h-3 bg-yellow-500 rounded-full animate-pulse shrink-0" title="正在准备引擎"></div>
                    <div class="relative w-36 sm:w-48">
                        <select id="modelSelect" onchange="handleModelSwitch()" class="block appearance-none w-full bg-gray-700 border border-gray-600 text-white py-1.5 pl-3 pr-8 rounded-lg shadow focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm font-medium cursor-pointer truncate">
                            <option value="">加载中...</option>
                        </select>
                        <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-gray-300">
                            <svg class="fill-current h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M9.293 12.95l.707.707L15.657 8l-1.414-1.414L10 10.828 5.757 6.586 4.343 8z"/></svg>
                        </div>
                    </div>
                    
                    <!-- ========== 新增：系统提示词按钮 ========== -->
                    <button onclick="openSystemPromptModal()" id="systemPromptBtn" class="p-1.5 sm:p-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors border border-gray-600 hover:border-blue-500/50" title="系统提示词设置">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="3"></circle>
                            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                        </svg>
                    </button>
                </div>
                
                <div class="flex items-center space-x-2">
                    <button onclick="exportChat()" class="text-gray-400 hover:text-white p-2 rounded-lg transition-colors" title="导出当前对话">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                    </button>
                    <button onclick="openChangePasswordModal()" class="text-gray-400 hover:text-white p-1.5 sm:px-3 sm:py-1.5 rounded-lg font-medium transition-colors flex items-center text-sm border border-gray-600 hover:border-yellow-500/50" title="修改密码">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 sm:mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0110 0v4"></path></svg>
                        <span class="hidden sm:inline">改密</span>
                    </button>
                    <button onclick="doLogout()" class="text-gray-400 hover:text-white p-1.5 sm:px-3 sm:py-1.5 rounded-lg font-medium transition-colors flex items-center text-sm border border-gray-600 hover:border-red-500/50" title="退出登录">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 sm:mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
                        <span class="hidden sm:inline">退出</span>
                    </button>
                    <button onclick="resetChat()" id="resetBtn" class="bg-red-500 hover:bg-red-600 text-white p-1.5 sm:px-3 sm:py-1.5 rounded-lg font-medium transition-colors flex items-center shadow-sm text-sm" title="强制重启底层进程">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 sm:mr-1" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd" /></svg>
                        <span class="hidden sm:inline">重启引擎</span>
                    </button>
                </div>
            </header>

            <main id="chatBox" class="flex-1 min-h-0 overflow-y-auto p-3 sm:p-6 md:p-8 space-y-4 sm:space-y-6 scroll-smooth"></main>

            <footer class="bg-gray-800 p-3 sm:p-4 border-t border-gray-700 shrink-0 safe-area-bottom w-full">
                <div class="max-w-4xl mx-auto relative flex items-end bg-gray-700 rounded-xl overflow-hidden border border-gray-600 focus-within:ring-2 focus-within:ring-blue-500 transition-shadow">
                    <textarea id="userInput" rows="1" class="w-full bg-transparent text-white text-base pl-4 pr-12 py-3 focus:outline-none resize-none overflow-y-auto max-h-32 min-h-[48px]" placeholder="输入问题，Enter 发送..."></textarea>
                    <button onclick="sendMessage()" id="sendBtn" class="absolute right-2 bottom-2 p-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-transform active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 transform rotate-90" viewBox="0 0 20 20" fill="currentColor"><path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" /></svg>
                    </button>
                </div>
            </footer>
        </div>

        <script>
            // --- 全局变量 ---
            let sessions = [];
            let currentSessionId = null;
            let isGenerating = false;
            let currentSystemPrompt = "";
            
            // --- 预设提示词 ---
            const PRESET_PROMPTS = {
                helpful: "你是一个乐于助人的AI助手。请用简洁、友好的语言回答问题，注重实用性。",
                coder: "你是一个专业的程序员，擅长Python、JavaScript、C++等多种编程语言。代码要求简洁规范，带有适当注释。回答格式：先解释思路，再给出代码示例。",
                teacher: "你是一位耐心的老师，擅长用通俗易懂的方式讲解知识。回答时注重由浅入深，循序渐进，可以举生活中的例子来帮助理解。",
                translator: "你是一个专业的翻译助手，精通中英文互译以及多种其他语言。翻译时注重信、达、雅，保持原文风格和语气。",
                expert: "你是一个专业顾问，擅长分析问题并提供专业建议。回答时条理清晰，有理有据，善于从多个角度分析问题。"
            };
            
            // --- DOM 元素 ---
            const chatBox = document.getElementById('chatBox');
            const userInput = document.getElementById('userInput');
            const sendBtn = document.getElementById('sendBtn');
            const modelSelect = document.getElementById('modelSelect');
            const statusDot = document.getElementById('statusDot');
            const sessionList = document.getElementById('sessionList');
            const sidebar = document.getElementById('sidebar');
            const mobileOverlay = document.getElementById('mobileOverlay');
            const systemPromptModal = document.getElementById('systemPromptModal');
            const systemPromptInput = document.getElementById('systemPromptInput');

            // --- 侧边栏切换 ---
            function toggleSidebar() {
                sidebar.classList.toggle('-translate-x-full');
                mobileOverlay.classList.toggle('hidden');
            }

            // --- 系统提示词相关函数 ---
            async function loadSystemPrompt() {
                try {
                    const res = await fetch('/api/system-prompt');
                    const data = await res.json();
                    currentSystemPrompt = data.content;
                    updatePromptCount();
                } catch(e) {
                    console.error("加载系统提示词失败:", e);
                }
            }
            
            function openSystemPromptModal() {
                systemPromptInput.value = currentSystemPrompt;
                updatePromptCount();
                systemPromptModal.classList.remove('modal-hidden');
            }
            
            function closeSystemPromptModal() {
                systemPromptModal.classList.add('modal-hidden');
            }
            
            function updatePromptCount() {
                const len = systemPromptInput.value.length;
                document.getElementById('promptCount').textContent = `${len} / 2000 字符`;
            }
            
            async function saveSystemPrompt() {
                const content = systemPromptInput.value.trim();
                try {
                    const res = await fetch('/api/system-prompt', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ content })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        currentSystemPrompt = content;
                        closeSystemPromptModal();
                        // 显示保存成功提示
                        const toast = document.createElement('div');
                        toast.className = 'fixed top-4 right-4 bg-green-600 text-white px-4 py-2 rounded-lg shadow-lg z-50 animate-pulse';
                        toast.textContent = '✅ 系统提示词已保存';
                        document.body.appendChild(toast);
                        setTimeout(() => toast.remove(), 2000);
                    }
                } catch(e) {
                    alert('保存失败: ' + e.message);
                }
            }
            
            function setPresetPrompt(key) {
                systemPromptInput.value = PRESET_PROMPTS[key] || '';
                updatePromptCount();
            }
            
            function clearPrompt() {
                systemPromptInput.value = '';
                updatePromptCount();
            }

            // 点击弹窗外部关闭
            systemPromptModal.addEventListener('click', function(e) {
                if (e.target === systemPromptModal) {
                    closeSystemPromptModal();
                }
            });

            // --- 登录/退出函数 ---
            async function doLogin() {
                const username = document.getElementById('loginUsername').value.trim();
                const password = document.getElementById('loginPassword').value;
                const btn = document.getElementById('loginBtn');
                const err = document.getElementById('loginError');
                
                if (!username || !password) {
                    err.textContent = '请输入用户名和密码';
                    err.classList.remove('hidden');
                    return;
                }
                
                btn.disabled = true;
                btn.textContent = '登录中...';
                err.classList.add('hidden');
                
                try {
                    const res = await fetch('/api/auth/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username, password })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        document.getElementById('loginOverlay').classList.add('hidden');
                        await initModels();
                        await loadSessions();
                        await loadSystemPrompt();
                    } else {
                        err.textContent = data.message || '登录失败';
                        err.classList.remove('hidden');
                    }
                } catch(e) {
                    err.textContent = '网络错误，请重试';
                    err.classList.remove('hidden');
                } finally {
                    btn.disabled = false;
                    btn.textContent = '登 录';
                }
            }
            
            async function doLogout() {
                await fetch('/api/auth/logout', { method: 'POST' });
                chatBox.innerHTML = '';
                sessionList.innerHTML = '';
                currentSessionId = null;
                sessions = [];
                document.getElementById('loginOverlay').classList.remove('hidden');
                document.getElementById('loginPassword').value = '';
            }
            
            // --- 修改密码函数 ---
            function openChangePasswordModal() {
                document.getElementById('oldPassword').value = '';
                document.getElementById('newPassword').value = '';
                document.getElementById('confirmPassword').value = '';
                document.getElementById('changePwdError').classList.add('hidden');
                document.getElementById('changePwdSuccess').classList.add('hidden');
                document.getElementById('changePwdModal').classList.remove('modal-hidden');
                document.getElementById('oldPassword').focus();
            }
            
            function closeChangePasswordModal() {
                document.getElementById('changePwdModal').classList.add('modal-hidden');
            }
            
            async function doChangePassword() {
                const oldPwd = document.getElementById('oldPassword').value;
                const newPwd = document.getElementById('newPassword').value;
                const confirmPwd = document.getElementById('confirmPassword').value;
                const btn = document.getElementById('changePwdBtn');
                const err = document.getElementById('changePwdError');
                const succ = document.getElementById('changePwdSuccess');
                
                err.classList.add('hidden');
                succ.classList.add('hidden');
                
                if (!oldPwd || !newPwd) {
                    err.textContent = '请填写所有密码字段';
                    err.classList.remove('hidden');
                    return;
                }
                if (newPwd.length < 4) {
                    err.textContent = '新密码至少需要4个字符';
                    err.classList.remove('hidden');
                    return;
                }
                if (newPwd !== confirmPwd) {
                    err.textContent = '两次输入的新密码不一致';
                    err.classList.remove('hidden');
                    return;
                }
                if (oldPwd === newPwd) {
                    err.textContent = '新密码不能与原密码相同';
                    err.classList.remove('hidden');
                    return;
                }
                
                btn.disabled = true;
                btn.textContent = '修改中...';
                
                try {
                    const res = await fetch('/api/auth/change-password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ old_password: oldPwd, new_password: newPwd })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        succ.textContent = '密码修改成功！';
                        succ.classList.remove('hidden');
                        setTimeout(() => closeChangePasswordModal(), 1500);
                    } else {
                        err.textContent = data.message || '修改失败';
                        err.classList.remove('hidden');
                    }
                } catch(e) {
                    err.textContent = '网络错误，请重试';
                    err.classList.remove('hidden');
                } finally {
                    btn.disabled = false;
                    btn.textContent = '确认修改';
                }
            }
            
            // 点击弹窗外部关闭
            document.getElementById('changePwdModal').addEventListener('click', function(e) {
                if (e.target === document.getElementById('changePwdModal')) {
                    closeChangePasswordModal();
                }
            });
            
            // --- 其他函数保持不变 ---
            function cleanOutputText(text) {
                if (!text) return text;
                return text.replace(/(robot:|user:)\s*/gi, '').trimStart();
            }

            async function loadSessions() {
                try {
                    const res = await fetch('/api/sessions');
                    sessions = await res.json();
                    
                    if (sessions.length === 0) {
                        await createNewSession();
                    } else {
                        if (!currentSessionId || !sessions.find(s => s.id === currentSessionId)) {
                            currentSessionId = sessions[0].id;
                        }
                        renderSidebar();
                        await switchSession(currentSessionId);
                    }
                } catch(e) {
                    console.error("加载会话列表失败:", e);
                }
            }

            async function createNewSession() {
                if (isGenerating) return alert("正在生成回复中，请稍后再试");
                try {
                    const res = await fetch('/api/sessions', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: "新的聊天" })
                    });
                    const newSession = await res.json();
                    sessions.unshift(newSession);
                    currentSessionId = newSession.id;
                    renderSidebar();
                    renderChat([]);
                    if(window.innerWidth < 768) toggleSidebar();
                } catch(e) {
                    console.error("创建会话失败:", e);
                }
            }

            async function deleteSession(id, e) {
                e.stopPropagation();
                if (isGenerating) return;
                try {
                    await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
                    sessions = sessions.filter(s => s.id !== id);
                    if (currentSessionId === id) {
                        currentSessionId = sessions.length > 0 ? sessions[0].id : null;
                    }
                    if (sessions.length === 0) {
                        await createNewSession();
                    } else {
                        renderSidebar();
                        await switchSession(currentSessionId);
                    }
                } catch(e) {
                    console.error("删除会话失败:", e);
                }
            }

            async function switchSession(id) {
                if (isGenerating || !id) return;
                currentSessionId = id;
                renderSidebar();
                try {
                    const res = await fetch(`/api/sessions/${id}/messages`);
                    const messages = await res.json();
                    renderChat(messages);
                } catch(e) {
                    console.error("加载会话历史失败:", e);
                }
                if(window.innerWidth < 768 && !sidebar.classList.contains('-translate-x-full')) {
                    toggleSidebar();
                }
            }

            function renderSidebar() {
                sessionList.innerHTML = '';
                sessions.forEach(session => {
                    const isActive = session.id === currentSessionId;
                    const div = document.createElement('div');
                    div.className = `group flex justify-between items-center px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${isActive ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-700/50 hover:text-gray-200'}`;
                    div.onclick = () => switchSession(session.id);
                    div.innerHTML = `
                        <div class="flex items-center space-x-2 truncate flex-1 pr-2">
                            <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path></svg>
                            <span class="truncate text-sm font-medium">${session.title}</span>
                        </div>
                        <button onclick="deleteSession('${session.id}', event)" class="text-gray-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity p-1">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                        </button>
                    `;
                    sessionList.appendChild(div);
                });
            }

            function renderChat(messages) {
                chatBox.innerHTML = '';
                if (!messages || messages.length === 0) {
                    showWelcomeMessage(`RKLLM 引擎已就绪`);
                    return;
                }
                
                messages.forEach((msg, index) => {
                    const msgDiv = document.createElement('div');
                    msgDiv.className = `flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`;
                    
                    const colDiv = document.createElement('div');
                    colDiv.className = `flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'} max-w-[95%] sm:max-w-[85%]`;
                    
                    const bubble = document.createElement('div');
                    bubble.className = `rounded-2xl p-3 sm:p-4 prose prose-invert text-sm sm:text-base shadow-md ${msg.role === 'user' ? 'bg-blue-600 text-white rounded-tr-sm' : 'bg-gray-700 text-gray-100 rounded-tl-sm'}`;
                    
                    const displayContent = msg.role === 'assistant' ? cleanOutputText(msg.content) : msg.content;
                    
                    if (msg.role === 'user') bubble.innerText = displayContent;
                    else renderMarkdown(bubble, displayContent);
                    
                    colDiv.appendChild(bubble);
                    
                    if (index === messages.length - 1 && msg.role === 'assistant') {
                        const actionDiv = document.createElement('div');
                        actionDiv.className = 'mt-1.5 flex justify-start pl-1 regenerate-btn-container';
                        actionDiv.innerHTML = `
                            <button onclick="regenerateLast()" class="group flex items-center space-x-1.5 text-xs text-gray-400 hover:text-blue-400 transition-colors px-2.5 py-1.5 bg-gray-800/80 hover:bg-gray-800 rounded-lg border border-gray-700 hover:border-blue-500/50 shadow-sm cursor-pointer" title="重新生成回复">
                                <svg class="w-3.5 h-3.5 group-active:rotate-180 transition-transform duration-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                                <span>重新生成</span>
                            </button>
                        `;
                        colDiv.appendChild(actionDiv);
                    }
                    
                    msgDiv.appendChild(colDiv);
                    chatBox.appendChild(msgDiv);
                });
                setTimeout(() => chatBox.scrollTop = chatBox.scrollHeight, 50);
            }

            marked.setOptions({
                highlight: function(code, lang) {
                    const language = hljs.getLanguage(lang) ? lang : 'plaintext';
                    return hljs.highlight(code, { language }).value;
                }, breaks: true
            });

            async function initModels() {
                try {
                    const res = await fetch('/api/models');
                    const data = await res.json();
                    modelSelect.innerHTML = '';
                    data.models.forEach(m => {
                        const opt = document.createElement('option');
                        opt.value = m.id; opt.textContent = m.name;
                        if(m.id === data.current) opt.selected = true;
                        modelSelect.appendChild(opt);
                    });
                    setTimeout(() => updateStatus('ready', 'NPU 引擎就绪'), 2000);
                } catch(e) {
                    updateStatus('error', '获取模型失败');
                }
            }
            
            window.addEventListener('DOMContentLoaded', async () => {
                // 先检查登录状态
                try {
                    const authRes = await fetch('/api/auth/status');
                    const authData = await authRes.json();
                    if (authData.authenticated) {
                        document.getElementById('loginOverlay').classList.add('hidden');
                        await initModels();
                        await loadSessions();
                        await loadSystemPrompt();
                    } else {
                        document.getElementById('loginOverlay').classList.remove('hidden');
                    }
                } catch(e) {
                    document.getElementById('loginOverlay').classList.remove('hidden');
                }
            });

            function updateStatus(status, text = '') {
                statusDot.className = 'w-3 h-3 rounded-full shrink-0 transition-colors duration-300';
                if (status === 'loading') { statusDot.classList.add('bg-yellow-500', 'animate-pulse'); modelSelect.disabled = true; }
                else if (status === 'ready') { statusDot.classList.add('bg-green-500', 'shadow-[0_0_8px_rgba(34,197,94,0.6)]'); modelSelect.disabled = false; }
                else if (status === 'error') { statusDot.classList.add('bg-red-500'); modelSelect.disabled = false; }
                if(text) statusDot.title = text;
            }

            async function handleModelSwitch() {
                if (isGenerating) return;
                const newModelId = modelSelect.value;
                const newModelName = modelSelect.options[modelSelect.selectedIndex].text;
                
                updateStatus('loading', '正在切换模型...');
                chatBox.innerHTML = `
                    <div class="flex justify-center mt-10">
                        <div class="text-center text-yellow-400 space-y-4 px-4">
                            <svg class="animate-spin w-12 h-12 mx-auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                            <p class="text-sm sm:text-base font-medium">正在加载 ${newModelName}...</p>
                        </div>
                    </div>`;

                try {
                    const res = await fetch('/api/switch', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ model_id: newModelId })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                        updateStatus('ready', '就绪');
                        await switchSession(currentSessionId);
                    } else throw new Error(data.message);
                } catch(e) {
                    updateStatus('error', '切换失败');
                    showWelcomeMessage(`模型切换失败: ${e.message}`, true);
                }
            }

            function showWelcomeMessage(text, isError = false) {
                const color = isError ? 'text-red-400' : 'text-gray-400';
                const icon = isError 
                    ? `<svg class="w-12 h-12 mx-auto text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`
                    : `<svg class="w-12 h-12 mx-auto text-blue-500 opacity-80" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>`;
                
                chatBox.innerHTML = `
                    <div class="flex justify-center mt-10 h-full items-center pb-20" id="welcomeMsg">
                        <div class="text-center space-y-4 px-4">
                            ${icon}
                            <h3 class="text-xl font-bold text-gray-200">欢迎使用 NPU 本地模型</h3>
                            <p class="text-sm ${color}">${text}</p>
                        </div>
                    </div>`;
            }

            function renderMarkdown(element, text) {
                const mathBlocks = [];
                let tempText = text.replace(/\$\$([\s\S]*?)\$\$/g, function(match) {
                    mathBlocks.push(match); return `MATHPLACEHOLDERBLOCK${mathBlocks.length - 1}END`;
                });
                tempText = tempText.replace(/\$([^\n\$]+?)\$/g, function(match) {
                    mathBlocks.push(match); return `MATHPLACEHOLDERINLINE${mathBlocks.length - 1}END`;
                });

                let html = marked.parse(tempText);
                html = html.replace(/MATHPLACEHOLDERBLOCK(\d+)END/g, (m, i) => mathBlocks[i]);
                html = html.replace(/MATHPLACEHOLDERINLINE(\d+)END/g, (m, i) => mathBlocks[i]);

                element.innerHTML = html;
                if (window.renderMathInElement) {
                    renderMathInElement(element, {
                        delimiters: [
                            {left: '$$', right: '$$', display: true}, {left: '\\[', right: '\\]', display: true},
                            {left: '$', right: '$', display: false}, {left: '\\(', right: '\\)', display: false}
                        ], throwOnError: false
                    });
                }
            }

            userInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
            });

            userInput.addEventListener('input', function() {
                this.style.height = 'auto';
                this.style.height = Math.min(this.scrollHeight, 128) + 'px';
                if(this.value === '') this.style.height = 'auto';
            });

            function appendMessageBubble(role, content) {
                const welcome = document.getElementById('welcomeMsg');
                if(welcome) welcome.remove();
                
                const msgDiv = document.createElement('div');
                msgDiv.className = `flex ${role === 'user' ? 'justify-end' : 'justify-start'}`;
                
                const colDiv = document.createElement('div');
                colDiv.className = `flex flex-col ${role === 'user' ? 'items-end' : 'items-start'} max-w-[95%] sm:max-w-[85%]`;

                const bubble = document.createElement('div');
                bubble.className = `rounded-2xl p-3 sm:p-4 prose prose-invert text-sm sm:text-base shadow-md ${role === 'user' ? 'bg-blue-600 text-white rounded-tr-sm' : 'bg-gray-700 text-gray-100 rounded-tl-sm'}`;
                
                const displayContent = role === 'assistant' ? cleanOutputText(content) : content;
                
                if (role === 'user') bubble.innerText = displayContent;
                else renderMarkdown(bubble, displayContent);
                
                colDiv.appendChild(bubble);
                msgDiv.appendChild(colDiv);
                chatBox.appendChild(msgDiv);
                
                setTimeout(() => chatBox.scrollTop = chatBox.scrollHeight, 50);
                return bubble;
            }

            async function triggerGeneration(queryText, isRegenerate = false) {
                if (isGenerating || statusDot.classList.contains('bg-yellow-500')) return;
                if (!currentSessionId) return;

                isGenerating = true; sendBtn.disabled = true; modelSelect.disabled = true;

                const oldBtns = chatBox.querySelectorAll('.regenerate-btn-container');
                oldBtns.forEach(btn => btn.remove());

                if (!isRegenerate) {
                    userInput.value = ''; userInput.style.height = 'auto';
                    if(window.innerWidth < 640) userInput.blur();
                    appendMessageBubble('user', queryText);
                } else {
                    const bubbles = chatBox.children;
                    if(bubbles.length > 0) {
                        const lastDiv = bubbles[bubbles.length-1];
                        if (lastDiv.querySelector('.bg-gray-700')) lastDiv.remove();
                    }
                }
                
                const assistantBubble = appendMessageBubble('assistant', '<span class="animate-pulse flex items-center space-x-2"><span>NPU 计算中</span><span class="flex space-x-1"><span class="w-1 h-1 bg-gray-400 rounded-full animate-bounce"></span><span class="w-1 h-1 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.2s"></span><span class="w-1 h-1 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.4s"></span></span></span>');
                let fullResponse = "";

                try {
                    const response = await fetch('/api/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            session_id: currentSessionId, 
                            query: queryText,
                            regenerate: isRegenerate
                        })
                    });

                    const reader = response.body.getReader();
                    const decoder = new TextDecoder("utf-8");
                    assistantBubble.innerHTML = ''; 

                    let buffer = '';
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        
                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n');
                        buffer = lines.pop();

                        for (const line of lines) {
                            if (line.startsWith('data: ')) {
                                const dataStr = line.slice(6).trim();
                                if (dataStr === '[DONE]') break;
                                if (dataStr) {
                                    try {
                                        const data = JSON.parse(dataStr);
                                        fullResponse += data.content;
                                        renderMarkdown(assistantBubble, cleanOutputText(fullResponse));
                                        chatBox.scrollTop = chatBox.scrollHeight;
                                    } catch(e) { }
                                }
                            }
                        }
                    }
                    
                    const sessionRes = await fetch('/api/sessions');
                    sessions = await sessionRes.json();
                    renderSidebar();
                    
                    isGenerating = false;
                    await switchSession(currentSessionId);

                } catch (error) {
                    renderMarkdown(assistantBubble, "⚠️ 网络错误或 NPU 后端异常。");
                } finally {
                    isGenerating = false; sendBtn.disabled = false; modelSelect.disabled = false;
                }
            }

            async function sendMessage() {
                const text = userInput.value.trim();
                if (!text) return;
                triggerGeneration(text, false);
            }

            function regenerateLast() {
                triggerGeneration("", true);
            }

            async function resetChat() {
                if(isGenerating) return;
                updateStatus('loading', '正在重启 NPU 进程...');
                const modelName = modelSelect.options[modelSelect.selectedIndex].text;

                chatBox.innerHTML = `
                    <div class="flex justify-center mt-10">
                        <div class="text-center text-blue-400 space-y-4 px-4">
                            <svg class="animate-spin w-12 h-12 mx-auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                            <p class="text-sm">正在强制清理 NPU 碎片并重启进程...</p>
                        </div>
                    </div>`;
                
                await fetch('/api/reset', { method: 'POST' });
                
                updateStatus('ready', '就绪');
                await switchSession(currentSessionId); 
            }

            async function exportChat() {
                if (!currentSessionId) return;
                try {
                    const res = await fetch(`/api/sessions/${currentSessionId}/messages`);
                    const messages = await res.json();
                    if (messages.length === 0) return alert("当前聊天暂无数据可导出");
                    
                    const sessionInfo = sessions.find(s => s.id === currentSessionId);
                    const title = sessionInfo ? sessionInfo.title : "Chat";
                    
                    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(messages, null, 2));
                    const downloadAnchorNode = document.createElement('a');
                    downloadAnchorNode.setAttribute("href", dataStr);
                    downloadAnchorNode.setAttribute("download", `RKLLM_${title}_${Date.now()}.json`);
                    document.body.appendChild(downloadAnchorNode);
                    downloadAnchorNode.click();
                    downloadAnchorNode.remove();
                } catch(e) {
                    alert("导出失败");
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
