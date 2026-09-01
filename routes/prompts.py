"""提示词库管理 API－增删改查"""
import sqlite3
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from config import DB_FILE
from routes.auth import require_auth

router = APIRouter(prefix="/api/prompts", tags=["prompts"])

class PromptCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description='提示词名称 1-50字符')
    content: str = Field(..., min_length=1, max_length=2000, description='提示词内容 1-2000字符')

class PromptUpdate(BaseModel):
    name: str = None
    content: str = None

@router.get("", dependencies=[Depends(require_auth)])
def list_prompts():
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, name, content, sort_order, created_at, updated_at FROM custom_prompts ORDER BY sort_order, id")
        rows = [dict(r) for r in c.fetchall()]
    return {"prompts": rows}

@router.post("", dependencies=[Depends(require_auth)])
def create_prompt(req: PromptCreate):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO custom_prompts (name, content) VALUES (?, ?)",
                  (req.name, req.content))
        conn.commit()
        prompt_id = c.lastrowid
    return {"status": "success", "id": prompt_id}

@router.put("/{prompt_id}", dependencies=[Depends(require_auth)])
def update_prompt(prompt_id: int, req: PromptUpdate):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        updates = []
        params = []
        if req.name is not None:
            updates.append("name = ?")
            params.append(req.name)
        if req.content is not None:
            updates.append("content = ?")
            params.append(req.content)
        if not updates:
            return {"status": "error", "message": "没有要更新的字段"}
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(prompt_id)
        c.execute(f"UPDATE custom_prompts SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    return {"status": "success"}

@router.delete("/{prompt_id}", dependencies=[Depends(require_auth)])
def delete_prompt(prompt_id: int):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM custom_prompts WHERE id = ?", (prompt_id,))
        conn.commit()
    return {"status": "success"}

@router.post("/{prompt_id}/use", dependencies=[Depends(require_auth)])
def use_prompt(prompt_id: int):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT name, content FROM custom_prompts WHERE id = ?", (prompt_id,))
        row = c.fetchone()
        if not row:
            return {"status": "error", "message": "提示词不存在"}
        name, content = row
        c.execute("INSERT OR REPLACE INTO system_prompts (id, content, updated_at) VALUES (1, ?, CURRENT_TIMESTAMP)", (content,))
        conn.commit()
    return {"status": "success", "message": f"已激活: {name}"}
