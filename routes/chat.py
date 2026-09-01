"""
RKLLM NPU WebUI - 聊天路由 (核心)
处理用户消息、SSE 流式输出、上下文拼接。
"""

import asyncio
import json
import sqlite3
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import config
import knowledge
from config import DB_FILE, PROMPT_SIGN
from database import get_system_prompt, get_session_kb
import npu
from routes.auth import require_auth

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str
    query: str = Field("", min_length=0, max_length=4096, description='用户输入 1-4096字符')
    regenerate: bool = False


@router.post("/chat", dependencies=[Depends(require_auth)])
async def chat_endpoint(request: ChatRequest):
    """核心聊天接口 — SSE 流式返回"""
    system_prompt = get_system_prompt()

    # ---- 处理 regenerate / 新消息 ----
    if request.regenerate:
        clean_query = _handle_regenerate(request.session_id)
    else:
        clean_query = _handle_new_message(request.session_id, request.query)

    # ---- 知识库检索（会话绑定了知识库时）----
    kb_context = ""
    try:
        kb_id = get_session_kb(request.session_id)
        if kb_id:
            hits = await asyncio.to_thread(
                knowledge.retrieve, kb_id, clean_query, config.KB_TOP_K)
            if hits:
                kb_context = "\n".join(
                    f"[{i + 1}] {h['content']}" for i, h in enumerate(hits))
                print(f"[kb] session={request.session_id} hits={len(hits)}")
    except Exception as e:
        print(f"[kb] retrieve error: {e}")

    # ---- 加载历史上下文 ----
    history_for_prompt = _load_history(request.session_id, clean_query)

    async def generate():
        async for sse in _generate_rkllm(
            clean_query, system_prompt, history_for_prompt,
            request.session_id, kb_context,
        ):
            yield sse

    return StreamingResponse(generate(), media_type="text/event-stream")


# ============================================================
#  rkllm 引擎 (llm_demo 常驻)
# ============================================================

async def _generate_rkllm(
    clean_query: str,
    system_prompt: str,
    history_for_prompt: list,
    session_id: str,
    kb_context: str = "",
):
    """rkllm 引擎的 SSE 生成器"""
    async with npu.llm_lock:
        try:
            if not npu.llm_process or npu.llm_process.returncode is not None:
                raise RuntimeError("NPU Process dead")

            # 检测会话切换 -> 重启 NPU
            if session_id != npu.active_session_id:
                print(f"\n[switch] {npu.active_session_id} -> {session_id}, restarting NPU...")
                await npu.start_llm()
                npu.active_session_id = session_id

            # 拼接上下文
            actual_query = _build_rkllm_prompt(
                clean_query, system_prompt, history_for_prompt, kb_context)

            npu.llm_process.stdin.write(
                (actual_query + "\n").encode("utf-8"))
            await npu.llm_process.stdin.drain()

        except Exception as e:
            print(f"write error: {e}")
            yield (
                "data: " + json.dumps(
                    {"content": "NPU process not ready, restarting..."},
                    ensure_ascii=False) + "\n\n"
            )
            await npu.start_llm()
            return

        # 流式读取输出（计时统计）
        byte_buffer = b""
        full_response_text = ""
        chunk_buffer = ""
        is_first_chunk = True
        t_start = time.time()
        response_chars = 0

        while True:
            try:
                char = await npu.llm_process.stdout.read(1)
                if not char:
                    break

                byte_buffer += char
                try:
                    text_chunk = byte_buffer.decode("utf-8")
                    byte_buffer = b""
                    full_response_text += text_chunk

                    if full_response_text.endswith(PROMPT_SIGN):
                        elapsed = int((time.time() - t_start) * 1000)
                        if elapsed > 0 and response_chars > 0:
                            yield "data: " + json.dumps(
                                {"type": "stats", "chars": response_chars, "time_ms": elapsed},
                                ensure_ascii=False) + "\n\n"
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

                    if not text_chunk and is_first_chunk:
                        continue

                    chunk_buffer += text_chunk
                    if chunk_buffer:
                        safe_to_send = chunk_buffer
                        for i in range(1, len(PROMPT_SIGN) + 1):
                            if chunk_buffer.endswith(PROMPT_SIGN[:i]):
                                safe_to_send = chunk_buffer[:-i]
                                break

                        if safe_to_send:
                            response_chars += len(safe_to_send)
                            yield "data: " + json.dumps(
                                {"content": safe_to_send},
                                ensure_ascii=False) + "\n\n"
                            chunk_buffer = chunk_buffer[len(safe_to_send):]

                except UnicodeDecodeError:
                    continue
            except Exception as e:
                print(f"read error: {e}")
                break

        # 保存到 DB
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, "assistant", full_response_text))
            conn.commit()


# ============================================================
#  Prompt 构建
# ============================================================

def _build_rkllm_prompt(clean_query, system_prompt, history, kb_context="") -> str:
    """构建 rkllm 引擎的 prompt 字符串"""
    prefix = ""
    if kb_context:
        prefix = "【知识库参考】\n" + kb_context + "\n\n"
    if history:
        context_str = prefix + (
            "【系统设定】" + system_prompt +
            "【请参考以下历史对话上下文】"
        )
        for msg in history:
            role_name = "User" if msg["role"] == "user" else "AI"
            safe_content = msg["content"].replace("\n", " ").replace("\r", " ")
            if len(safe_content) > 1500:
                safe_content = safe_content[:1500] + " ...[truncated]"
            context_str += f" {role_name}: {safe_content} |"
        context_str += (
            f" 【结合上述历史上下文和系统设定，请直接回答我的最新问题】 "
            f"User: {clean_query} AI:"
        )
        print(f"\n[prompt] context built, total: {len(context_str)} chars")
        return context_str
    else:
        context_str = prefix + "【系统设定】" + system_prompt + f" User: {clean_query} AI:"
        print(f"\n[prompt] no history, total: {len(context_str)} chars")
        return context_str

# ============================================================
#  DB 辅助函数
# ============================================================

def _handle_regenerate(session_id: str) -> str:
    """重新生成：删除最后一条 assistant，取上一条 user"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id, role, content FROM messages WHERE session_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (session_id,))
        last_msg = c.fetchone()
        if last_msg and last_msg[1] == "assistant":
            c.execute("DELETE FROM messages WHERE id = ?", (last_msg[0],))
            conn.commit()
        c.execute(
            "SELECT content FROM messages WHERE session_id = ? AND role = 'user' "
            "ORDER BY id DESC LIMIT 1",
            (session_id,))
        user_msg = c.fetchone()
        return user_msg[0] if user_msg else ""


def _handle_new_message(session_id: str, query: str) -> str:
    """保存新消息到 DB，自动生成 session 标题"""
    clean_query = query.replace("\n", " ").replace("\r", " ").strip()
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, "user", clean_query))
        c.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?",
                  (session_id,))
        if c.fetchone()[0] == 1:
            new_title = clean_query[:15] + ("..." if len(clean_query) > 15 else "")
            c.execute(
                "UPDATE sessions SET title = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?", (new_title, session_id))
        else:
            c.execute(
                "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?", (session_id,))
        conn.commit()
    return clean_query


def _load_history(session_id: str, clean_query: str) -> list:
    """加载最近 6 条历史消息"""
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT role, content FROM messages WHERE session_id = ? "
            "ORDER BY id DESC LIMIT 6",
            (session_id,))
        recent_history = list(reversed([dict(r) for r in c.fetchall()]))
        if (recent_history and recent_history[-1]["role"] == "user"
                and recent_history[-1]["content"] == clean_query):
            return recent_history[:-1]
        return recent_history
