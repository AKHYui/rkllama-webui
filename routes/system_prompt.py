"""
RKLLM NPU WebUI - 系统提示词路由
读取和保存全局系统提示词。
"""

import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from config import DB_FILE, DEFAULT_SYSTEM_PROMPT
from routes.auth import require_auth

router = APIRouter(prefix="/api/system-prompt", tags=["system-prompt"])


class SystemPromptRequest(BaseModel):
    content: str


@router.get("", dependencies=[Depends(require_auth)])
def get_system_prompt_api():
    """获取当前系统提示词"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT content FROM system_prompts WHERE id = 1")
        row = c.fetchone()
        content = row[0] if row else DEFAULT_SYSTEM_PROMPT
    return {"content": content}


@router.post("", dependencies=[Depends(require_auth)])
def save_system_prompt(req: SystemPromptRequest):
    """保存系统提示词"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO system_prompts (id, content, updated_at) "
            "VALUES (1, ?, CURRENT_TIMESTAMP)",
            (req.content,))
        conn.commit()
    return {"status": "success", "message": "系统提示词已保存"}
