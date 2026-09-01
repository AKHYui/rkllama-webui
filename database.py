"""
RKLLM NPU WebUI - 数据库层
SQLite 初始化、表创建、系统提示词查询。
"""

import hashlib
import secrets
import sqlite3

from config import DB_FILE, DEFAULT_SYSTEM_PROMPT


def init_db():
    """初始化 SQLite 数据库，创建所有表并填充默认数据"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()

        # 会话表
        c.execute('''CREATE TABLE IF NOT EXISTS sessions
                     (id TEXT PRIMARY KEY, title TEXT,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

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

        # 用户认证表 (id=1 单例)
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY CHECK (id = 1),
                      username TEXT NOT NULL UNIQUE,
                      password_hash TEXT NOT NULL,
                      salt TEXT NOT NULL, session_token TEXT)''')

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
