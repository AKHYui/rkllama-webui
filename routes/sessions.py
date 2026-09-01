"""
RKLLM NPU WebUI - 会话管理路由
会话的创建、列表、删除、消息查询。
"""

import sqlite3
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config import DB_FILE
from routes.auth import require_auth

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    title: str = Field("新的聊天", max_length=100, description='会话标题 最多100字符')


@router.get("", dependencies=[Depends(require_auth)])
def get_sessions():
    """列出所有会话，按更新时间倒序"""
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM sessions ORDER BY updated_at DESC")
        return [dict(row) for row in c.fetchall()]


@router.post("", dependencies=[Depends(require_auth)])
def create_session(req: SessionCreate):
    """创建新会话"""
    session_id = str(uuid.uuid4())[:8]
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO sessions (id, title) VALUES (?, ?)",
                  (session_id, req.title))
        conn.commit()
    return {"id": session_id, "title": req.title}


@router.delete("/{session_id}", dependencies=[Depends(require_auth)])
def delete_session(session_id: str):
    """删除会话及其所有消息"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.commit()
    return {"status": "success"}


@router.get("/{session_id}/messages", dependencies=[Depends(require_auth)])
def get_messages(session_id: str):
    """获取指定会话的全部消息"""
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,))
        return [dict(row) for row in c.fetchall()]
