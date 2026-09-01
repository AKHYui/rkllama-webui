"""
RKLLM NPU WebUI - 知识库路由
知识库增删改查、文档上传/粘贴/删除、检索测试、会话绑定。
"""

import asyncio
import os
import uuid

from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel, Field

import config
import knowledge
from database import (
    get_kbs, get_kb_by_id, kb_name_exists, add_kb, update_kb, delete_kb,
    get_kb_documents, get_kb_document, add_kb_document, delete_kb_document,
    set_session_kb, get_session_kb,
)
from routes.auth import require_auth

router = APIRouter(prefix="/api", tags=["knowledge"])

ALLOWED_EXTS = (".txt", ".md")


class KBCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: str = Field("", max_length=200)


class DocumentText(BaseModel):
    filename: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1)


class SessionKBRequest(BaseModel):
    kb_id: int | None = None


class TestRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(config.KB_TOP_K, ge=1, le=10)


def _ingest(kb_id, filename, content):
    """解析文本 -> 分块 -> 向量入库 -> 记录文档"""
    if not content.strip():
        return {"status": "error", "message": "文档内容为空"}
    chunks = knowledge.chunk_text(content)
    if not chunks:
        return {"status": "error", "message": "文档内容无法分块"}
    doc_id = uuid.uuid4().hex[:8]
    knowledge.add_document(kb_id, doc_id, chunks)
    add_kb_document(kb_id, filename, content, len(chunks))
    return {"status": "success", "chunk_count": len(chunks)}


@router.get("/kbs", dependencies=[Depends(require_auth)])
async def list_kbs():
    return {"kbs": get_kbs()}


@router.post("/kbs", dependencies=[Depends(require_auth)])
async def create_kb(req: KBCreate):
    if kb_name_exists(req.name):
        return {"status": "error", "message": f"知识库名 {req.name} 已存在"}
    kb_id = add_kb(req.name, req.description)
    return {"status": "success", "id": kb_id}


@router.put("/kbs/{kb_id}", dependencies=[Depends(require_auth)])
async def update_kb_endpoint(kb_id: int, req: KBCreate):
    kb = get_kb_by_id(kb_id)
    if not kb:
        return {"status": "error", "message": "知识库不存在"}
    other = get_kbs()
    if any(k["id"] != kb_id and k["name"] == req.name for k in other):
        return {"status": "error", "message": f"知识库名 {req.name} 已存在"}
    update_kb(kb_id, req.name, req.description)
    return {"status": "success"}


@router.delete("/kbs/{kb_id}", dependencies=[Depends(require_auth)])
async def delete_kb_endpoint(kb_id: int):
    if not get_kb_by_id(kb_id):
        return {"status": "error", "message": "知识库不存在"}
    knowledge.delete_collection(kb_id)
    delete_kb(kb_id)
    return {"status": "success"}


@router.get("/kbs/{kb_id}/documents", dependencies=[Depends(require_auth)])
async def list_documents(kb_id: int):
    if not get_kb_by_id(kb_id):
        return {"status": "error", "message": "知识库不存在"}
    return {"documents": get_kb_documents(kb_id)}


@router.post("/kbs/{kb_id}/documents", dependencies=[Depends(require_auth)])
async def upload_document(kb_id: int, file: UploadFile = File(...)):
    kb = get_kb_by_id(kb_id)
    if not kb:
        return {"status": "error", "message": "知识库不存在"}
    filename = (file.filename or "document").strip()
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        return {"status": "error", "message": "仅支持 txt/md 文件"}
    data = await file.read()
    if len(data) > config.KB_MAX_FILE_SIZE:
        return {"status": "error", "message": "文件超过 5MB 限制"}
    content = data.decode("utf-8", errors="replace")
    try:
        return await asyncio.to_thread(_ingest, kb_id, filename, content)
    except RuntimeError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": "入库失败: " + str(e)}


@router.post("/kbs/{kb_id}/documents/text", dependencies=[Depends(require_auth)])
async def upload_document_text(kb_id: int, req: DocumentText):
    kb = get_kb_by_id(kb_id)
    if not kb:
        return {"status": "error", "message": "知识库不存在"}
    try:
        return await asyncio.to_thread(_ingest, kb_id, req.filename, req.content)
    except RuntimeError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": "入库失败: " + str(e)}


@router.delete("/kbs/{kb_id}/documents/{doc_id}", dependencies=[Depends(require_auth)])
async def delete_document_endpoint(kb_id: int, doc_id: int):
    doc = get_kb_document(doc_id)
    if not doc or doc["kb_id"] != kb_id:
        return {"status": "error", "message": "文档不存在"}
    knowledge.delete_document(kb_id, str(doc_id))
    delete_kb_document(doc_id)
    return {"status": "success"}


@router.post("/kbs/{kb_id}/test", dependencies=[Depends(require_auth)])
async def test_retrieval(kb_id: int, req: TestRequest):
    try:
        hits = await asyncio.to_thread(knowledge.retrieve, kb_id, req.query, req.top_k)
        return {"status": "success", "hits": hits}
    except RuntimeError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": "检索失败: " + str(e)}


@router.get("/sessions/{session_id}/kb", dependencies=[Depends(require_auth)])
async def get_session_kb_endpoint(session_id: str):
    return {"kb_id": get_session_kb(session_id)}


@router.post("/sessions/{session_id}/kb", dependencies=[Depends(require_auth)])
async def bind_session_kb(session_id: str, req: SessionKBRequest):
    if req.kb_id is not None and not get_kb_by_id(req.kb_id):
        return {"status": "error", "message": "知识库不存在"}
    set_session_kb(session_id, req.kb_id)
    return {"status": "success"}