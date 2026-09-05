"""
RKLLM NPU WebUI - OpenAI 兼容接口（/v1）

对外提供 OpenAI 风格的调用方式，让外部工具（Chatbox / LobeChat / OpenAI SDK /
各类 Agent 框架）能通过 API-Key + 模型 id 调用板子上的 RKLLM 大模型。

设计要点：
- 鉴权：Authorization: Bearer <API-KEY>（与 WebUI 的 Session 认证相互独立）。
- 无状态：每次请求带完整 messages，语义上等于"全新上下文"，因此每次请求
  都会重启 NPU 引擎（清空 KV cache）。这是 RKLLM 有状态引擎的固有限制。
- 并发：共享 npu.llm_lock，全局串行（并发量 = 1），上一个任务未结束则排队等待。
- 状态隔离：请求结束后重置 npu.active_session_id，避免污染 WebUI 会话状态。
"""

import asyncio
import json
import secrets
import time

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Union

import npu
from config import PROMPT_SIGN
from database import get_models, get_model_by_id, verify_api_key
from routes.chat import _build_rkllm_prompt

router = APIRouter(prefix="/v1", tags=["openai"])


# ============================================================
#  鉴权（Bearer API-Key）
# ============================================================

async def require_api_key(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing API key. 请通过 Authorization: Bearer <API-KEY> 传入，"
                   "或到 WebUI 的「更多 → 外部调用」中创建 API-Key")
    key = auth[7:].strip()
    if not verify_api_key(key):
        raise HTTPException(status_code=401, detail="Invalid API key")


# ============================================================
#  请求模型
# ============================================================

class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = ""


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(None, ge=1)
    stream: bool = False
    stop: Optional[Union[str, List[str]]] = None
    n: int = 1


# ============================================================
#  messages -> prompt 转换
# ============================================================

def _convert_messages(messages: List[ChatMessage]):
    """把 OpenAI messages 转为 (system_prompt, history, query)

    - role=system 的消息合并为系统提示词
    - 其余 user/assistant 作为历史
    - 最后一条 user 作为当前查询
    """
    system_parts = []
    history = []
    for m in messages:
        content = (m.content or "").strip()
        if not content:
            continue
        if m.role == "system":
            system_parts.append(content)
        elif m.role in ("user", "assistant"):
            history.append({"role": m.role, "content": content})

    system_prompt = "\n".join(system_parts)
    query = ""
    if history and history[-1]["role"] == "user":
        query = history.pop()["content"]
    return system_prompt, history, query


# ============================================================
#  引擎调用（共享锁 + 请求级重启 + 状态重置）
# ============================================================

async def _engine_text_stream(prompt: str, model_id: str, overrides: dict):
    """持有全局锁，重启引擎并注入 prompt，逐片 yield 干净文本。

    生成期间全程持锁，保证与 WebUI 聊天全局串行；结束后重置 active_session_id。
    """
    async with npu.llm_lock:
        try:
            ok = await npu.start_llm(model_id=model_id, overrides=overrides)
            if not ok or not npu.llm_process or npu.llm_process.returncode is not None:
                yield "[引擎未就绪] 请确认 llm_demo 已安装且模型路径正确"
                return

            npu.llm_process.stdin.write((prompt + "\n").encode("utf-8"))
            await npu.llm_process.stdin.drain()

            byte_buffer = b""
            full_text = ""
            chunk_buffer = ""
            is_first_chunk = True

            while True:
                char = await npu.llm_process.stdout.read(1)
                if not char:
                    break
                byte_buffer += char
                try:
                    text_chunk = byte_buffer.decode("utf-8")
                    byte_buffer = b""
                    full_text += text_chunk

                    if full_text.endswith(PROMPT_SIGN):
                        break

                    if is_first_chunk:
                        if "robot:" in full_text:
                            text_chunk = full_text.split("robot:")[-1].lstrip()
                            is_first_chunk = False
                        elif len(full_text) > 15:
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
                            chunk_buffer = chunk_buffer[len(safe_to_send):]
                            yield safe_to_send

                except UnicodeDecodeError:
                    continue
                except Exception:
                    break
        finally:
            # 请求结束后重置会话标记，让 WebUI 下次请求自动识别"会话切换"并重启恢复
            npu.active_session_id = None


# ============================================================
#  SSE / JSON 格式化
# ============================================================

def _sse_chunk(cid, created, model, delta, finish_reason):
    payload = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数（RKLLM 不吐真实 token，按字符数/3 估算）"""
    return max(1, len(text or "") // 3)


def _build_overrides(req: ChatCompletionRequest) -> dict:
    overrides = {}
    if req.max_tokens is not None:
        overrides["max_tokens"] = req.max_tokens
    if req.temperature is not None:
        overrides["temperature"] = req.temperature
    if req.top_p is not None:
        overrides["top_p"] = req.top_p
    return overrides


# ============================================================
#  路由
# ============================================================

@router.get("/models", dependencies=[Depends(require_api_key)])
async def list_models():
    """列出可用模型（OpenAI 格式）。鉴权：同样要求有效 API-Key。"""
    models = get_models()
    data = [
        {"id": m["model_id"], "object": "model", "created": 0, "owned_by": "rkllm"}
        for m in models
    ]
    return {"object": "list", "data": data}


@router.post("/chat/completions", dependencies=[Depends(require_api_key)])
async def chat_completions(req: ChatCompletionRequest):
    model = get_model_by_id(req.model)
    if not model:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{req.model}' not found. 可用模型见 GET /v1/models")

    system_prompt, history, query = _convert_messages(req.messages)
    if not query:
        raise HTTPException(
            status_code=400,
            detail="messages 中缺少 user 消息（至少需要一条 role=user 的内容）")

    prompt = _build_rkllm_prompt(query, system_prompt, history)
    overrides = _build_overrides(req)
    cid = "chatcmpl-" + secrets.token_hex(12)
    created = int(time.time())
    model_name = req.model

    if req.stream:
        async def generate():
            yield _sse_chunk(
                cid, created, model_name,
                {"role": "assistant", "content": ""}, None)
            async for text in _engine_text_stream(prompt, model_name, overrides):
                yield _sse_chunk(cid, created, model_name, {"content": text}, None)
            yield _sse_chunk(cid, created, model_name, {}, "stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    # 非流式：累积完整文本后一次性返回
    full = ""
    async for text in _engine_text_stream(prompt, model_name, overrides):
        full += text

    prompt_tokens = _estimate_tokens(prompt)
    completion_tokens = _estimate_tokens(full)
    return {
        "id": cid,
        "object": "chat.completion",
        "created": created,
        "model": model_name,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": full},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
