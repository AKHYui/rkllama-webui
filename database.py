"""
RKLLM NPU WebUI - 数据库层
SQLite 初始化、表创建、系统提示词查询。
"""

import hashlib
import secrets
import sqlite3

from config import DB_FILE, DEFAULT_SYSTEM_PROMPT, MODELS


def init_db():
    """初始化 SQLite 数据库，创建所有表并填充默认数据"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()

        # 会话表
        c.execute('''CREATE TABLE IF NOT EXISTS sessions
                     (id TEXT PRIMARY KEY, title TEXT,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # 旧库迁移：sessions 增加知识库绑定列
        c.execute("PRAGMA table_info(sessions)")
        if "kb_id" not in [row[1] for row in c.fetchall()]:
            c.execute("ALTER TABLE sessions ADD COLUMN kb_id TEXT")

        # 消息表
        c.execute('''CREATE TABLE IF NOT EXISTS messages
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
                      role TEXT, content TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # 系统提示词表 (id=1 单例)
        c.execute('''CREATE TABLE IF NOT EXISTS system_prompts
                     (id INTEGER PRIMARY KEY CHECK (id = 1),
                      content TEXT NOT NULL,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        c.execute("SELECT COUNT(*) FROM system_prompts")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO system_prompts (id, content) VALUES (1, ?)",
                     (DEFAULT_SYSTEM_PROMPT,))

        # ===== 自定义提示词库（多条记录） =====
        c.execute('''CREATE TABLE IF NOT EXISTS custom_prompts
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      name TEXT NOT NULL,
                      content TEXT NOT NULL,
                      sort_order INTEGER DEFAULT 0,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      UNIQUE(name, content))''')

        # 预设默认提示词（仅在表为空时插入）
        c.execute("SELECT COUNT(*) FROM custom_prompts")
        if c.fetchone()[0] == 0:
            default_prompts = [
                ("默认助手", "你是一个真诚、自然、有温度的聊天伙伴。你的回答应该像朋友间的对话——有主见、有态度、敢表达真实想法，不迎合、不说教、不刻意讨好。"),
                ("程序员", "你是一个专业的程序员，擅长Python等多种编程语言。代码要求简洁规范，带有适当注释。回答格式：先解释思路，再给出代码示例。"),
                ("老师", "你是一位耐心的老师，擅长用通俗易懂的方式讲解知识。回答时注重由浅入深，循序渐进，可以举生活中的例子来帮助理解。"),
                ("翻译官", "你是一个专业的翻译助手，精通中英文互译。翻译时注重信、达、雅，保持原文风格和语气。"),
                ("角色扮演", "你将扮演用户指定的角色。用该角色的口吻、思维方式和背景知识来回应用户。投入角色，展现角色的性格特点和说话风格。"),
            ]
            for i, (name, content) in enumerate(default_prompts):
                c.execute(
                    "INSERT INTO custom_prompts (name, content, sort_order) VALUES (?, ?, ?)",
                    (name, content, i))

        # ===== 模型挂载表 =====
        c.execute('''CREATE TABLE IF NOT EXISTS models
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      model_id TEXT NOT NULL UNIQUE,
                      name TEXT NOT NULL,
                      path TEXT NOT NULL,
                      ctx_max INTEGER NOT NULL DEFAULT 4096,
                      max_tokens INTEGER NOT NULL DEFAULT 1024,
                      engine TEXT NOT NULL DEFAULT 'rkllm',
                      temperature REAL,
                      top_p REAL,
                      repeat_penalty REAL,
                      sort_order INTEGER DEFAULT 0,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # 旧库迁移：models 增加采样参数字段
        c.execute("PRAGMA table_info(models)")
        mcols = [row[1] for row in c.fetchall()]
        for col, ddl in (("temperature", "REAL"), ("top_p", "REAL"), ("repeat_penalty", "REAL")):
            if col not in mcols:
                c.execute(f"ALTER TABLE models ADD COLUMN {col} {ddl}")

        # 首次初始化时从 config.MODELS 导入默认模型
        c.execute("SELECT COUNT(*) FROM models")
        if c.fetchone()[0] == 0:
            for i, m in enumerate(MODELS):
                c.execute(
                    "INSERT INTO models (model_id, name, path, ctx_max, max_tokens, engine, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (m["id"], m["name"], m["path"],
                     m.get("ctx_max", 4096), m.get("max_tokens", 1024),
                     m.get("engine", "llama"), i))

        # 用户认证表 (id=1 单例)
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY CHECK (id = 1),
                      username TEXT NOT NULL UNIQUE,
                      password_hash TEXT NOT NULL,
                      salt TEXT NOT NULL, session_token TEXT)''')

        # ===== 知识库表 =====
        c.execute('''CREATE TABLE IF NOT EXISTS knowledge_bases
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      name TEXT NOT NULL UNIQUE,
                      description TEXT DEFAULT '',
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS kb_documents
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      kb_id INTEGER NOT NULL,
                      filename TEXT NOT NULL,
                      content TEXT NOT NULL,
                      chunk_count INTEGER DEFAULT 0,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # ===== 通用设置表 (key-value) =====
        c.execute('''CREATE TABLE IF NOT EXISTS settings
                     (key TEXT PRIMARY KEY,
                      value TEXT,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        c.execute("SELECT COUNT(*) FROM users")
        if c.fetchone()[0] == 0:
            salt = secrets.token_hex(16)
            default_password = "admin123"
            password_hash = hashlib.sha256(
                (default_password + salt).encode()).hexdigest()
            c.execute("INSERT INTO users (id, username, password_hash, salt) "
                      "VALUES (1, ?, ?, ?)", ("admin", password_hash, salt))

        conn.commit()
    print("[💾] SQLite 数据库初始化完成")


# 全局缓存，避免每次读 DB
_current_system_prompt = DEFAULT_SYSTEM_PROMPT


def get_system_prompt():
    """获取当前系统提示词（带缓存）"""
    global _current_system_prompt
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT content FROM system_prompts WHERE id = 1")
            row = c.fetchone()
            if row:
                _current_system_prompt = row[0]
    except Exception:
        pass
    return _current_system_prompt


# ===== Session Token 管理 =====

def get_user_session_token(username):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('SELECT session_token FROM users WHERE username = ?', (username,))
        row = c.fetchone()
        return row[0] if row else None


def set_user_session_token(username):
    token = secrets.token_hex(32)
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('UPDATE users SET session_token = ? WHERE username = ?',
                  (token, username))
        conn.commit()
    return token


def clear_user_session_token(username):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('UPDATE users SET session_token = NULL WHERE username = ?',
                  (username,))
        conn.commit()


def verify_session_token(username, token):
    if not token:
        return False
    stored = get_user_session_token(username)
    return stored is not None and stored == token


# ===== 模型挂载管理 =====

def get_models():
    """获取全部挂载模型（按 sort_order, id 排序）"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM models ORDER BY sort_order, id")
            return [dict(r) for r in c.fetchall()]
    except Exception:
        return []


def get_model_by_id(model_id):
    """按 model_id 获取模型，未找到返回 None"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM models WHERE model_id = ?", (model_id,))
            row = c.fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def model_id_exists(model_id):
    return get_model_by_id(model_id) is not None


def add_model(data):
    """新增模型，返回 {status, model}"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO models (model_id, name, path, ctx_max, max_tokens, engine, "
            "temperature, top_p, repeat_penalty) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (data["model_id"], data["name"], data["path"],
             data["ctx_max"], data["max_tokens"], data["engine"],
             data.get("temperature"), data.get("top_p"), data.get("repeat_penalty")))
        conn.commit()
    return {"status": "success", "model": get_model_by_id(data["model_id"])}


def update_model(model_id, data):
    """更新模型，返回 {status, model}"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE models SET name=?, path=?, ctx_max=?, max_tokens=?, engine=?, "
            "temperature=?, top_p=?, repeat_penalty=?, "
            "updated_at=CURRENT_TIMESTAMP WHERE model_id=?",
            (data["name"], data["path"], data["ctx_max"],
             data["max_tokens"], data["engine"],
             data.get("temperature"), data.get("top_p"), data.get("repeat_penalty"),
             model_id))
        conn.commit()
    return {"status": "success", "model": get_model_by_id(model_id)}


def delete_model(model_id):
    """删除模型，返回 {status}"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM models WHERE model_id = ?", (model_id,))
        conn.commit()
    return {"status": "success"}


# ===== 知识库管理 =====

def get_kbs():
    """获取全部知识库（含文档数）"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                "SELECT k.*, (SELECT COUNT(*) FROM kb_documents d WHERE d.kb_id = k.id) AS doc_count "
                "FROM knowledge_bases k ORDER BY k.id")
            return [dict(r) for r in c.fetchall()]
    except Exception:
        return []


def get_kb_by_id(kb_id):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM knowledge_bases WHERE id = ?", (kb_id,))
            row = c.fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def kb_name_exists(name):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM knowledge_bases WHERE name = ?", (name,))
            return c.fetchone()[0] > 0
    except Exception:
        return False


def add_kb(name, description=""):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO knowledge_bases (name, description) VALUES (?, ?)",
                  (name, description))
        conn.commit()
        return c.lastrowid


def update_kb(kb_id, name, description):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE knowledge_bases SET name=?, description=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (name, description, kb_id))
        conn.commit()


def delete_kb(kb_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM kb_documents WHERE kb_id = ?", (kb_id,))
        c.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
        c.execute("UPDATE sessions SET kb_id = NULL WHERE kb_id = ?", (kb_id,))
        conn.commit()


# ===== 知识库文档 =====

def get_kb_documents(kb_id):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                "SELECT id, kb_id, filename, chunk_count, created_at "
                "FROM kb_documents WHERE kb_id = ? ORDER BY id DESC", (kb_id,))
            return [dict(r) for r in c.fetchall()]
    except Exception:
        return []


def add_kb_document(kb_id, filename, content, chunk_count):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO kb_documents (kb_id, filename, content, chunk_count) VALUES (?, ?, ?, ?)",
            (kb_id, filename, content, chunk_count))
        conn.commit()
        return c.lastrowid


def get_kb_document(doc_id):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM kb_documents WHERE id = ?", (doc_id,))
            row = c.fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def delete_kb_document(doc_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM kb_documents WHERE id = ?", (doc_id,))
        conn.commit()


# ===== 会话知识库绑定 =====

def set_session_kb(session_id, kb_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE sessions SET kb_id = ? WHERE id = ?", (kb_id, session_id))
        conn.commit()


def get_session_kb(session_id):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT kb_id FROM sessions WHERE id = ?", (session_id,))
            row = c.fetchone()
            return row[0] if row else None
    except Exception:
        return None


# ===== 通用设置 (key-value) =====

def get_setting(key, default=None):
    """读取设置项，不存在返回 default"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = c.fetchone()
            return row[0] if row else default
    except Exception:
        return default


def set_setting(key, value):
    """写入设置项"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)", (key, value))
        conn.commit()
