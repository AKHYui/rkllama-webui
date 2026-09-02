"""
RKLLM NPU WebUI - 知识库向量模块
Embedding(bge-small-zh ONNX) + ChromaDB 持久化 + 分块/检索。
onnxruntime / chromadb / 模型缺失时优雅降级（如 Windows 开发机）。
"""

import os
import re

import config

EMBED_AVAILABLE = False

_sess = None
_tok = None


def _check_available():
    """检测向量栈组件与模型是否就绪"""
    global EMBED_AVAILABLE
    if EMBED_AVAILABLE:
        return True
    try:
        import onnxruntime  # noqa: F401
        import chromadb  # noqa: F401
        if os.path.isfile(os.path.join(config.EMBED_MODEL_DIR, "model.onnx")) \
                and os.path.isfile(os.path.join(config.EMBED_MODEL_DIR, "tokenizer.json")):
            EMBED_AVAILABLE = True
    except Exception:
        EMBED_AVAILABLE = False
    return EMBED_AVAILABLE


def _load():
    """加载 onnx 会话与 tokenizer（惰性，只加载一次）"""
    global _sess, _tok
    if _sess is not None:
        return _sess, _tok
    import onnxruntime as ort
    from tokenizers import Tokenizer
    _tok = Tokenizer.from_file(os.path.join(config.EMBED_MODEL_DIR, "tokenizer.json"))
    # 只保留 error 级别日志，屏蔽 RK3588 上无 GPU 导致的 device discovery 噪音
    _opts = ort.SessionOptions()
    _opts.log_severity_level = 3
    _sess = ort.InferenceSession(
        os.path.join(config.EMBED_MODEL_DIR, "model.onnx"),
        _opts, providers=["CPUExecutionProvider"])
    return _sess, _tok


def _get_client():
    """每次操作新建 PersistentClient，避免进程内缓存过期导致
    'Could not connect to tenant' 等目录状态错乱问题"""
    import chromadb
    return chromadb.PersistentClient(path=config.CHROMA_DIR)


def _get_collection(kb_id):
    return _get_client().get_or_create_collection(name=f"kb_{kb_id}")


def embed(texts):
    """文本列表 -> 512 维归一化向量 (mean pooling)"""
    import numpy as np
    sess, tok = _load()
    encs = tok.encode_batch(texts, add_special_tokens=True)
    max_len = max(len(e.ids) for e in encs)
    ids = np.zeros((len(encs), max_len), dtype=np.int64)
    mask = np.zeros_like(ids)
    types = np.zeros_like(ids)
    for i, e in enumerate(encs):
        ids[i, :len(e.ids)] = e.ids
        mask[i, :len(e.ids)] = e.attention_mask
        types[i, :len(e.ids)] = e.type_ids
    out = sess.run(["last_hidden_state"],
                   {"input_ids": ids, "attention_mask": mask, "token_type_ids": types})[0]
    m = np.expand_dims(mask, -1).astype(np.float32)
    pooled = (out * m).sum(1) / np.clip(m.sum(1), 1, None)
    return pooled / np.linalg.norm(pooled, axis=1, keepdims=True)


def chunk_text(text, size=None, overlap=None):
    """按段落 + 字符硬切分块"""
    size = size or config.KB_CHUNK_SIZE
    overlap = overlap or config.KB_CHUNK_OVERLAP
    text = re.sub(r"\r\n", "\n", text)
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks = []
    buf = ""
    for p in paragraphs:
        if not buf:
            buf = p
        elif len(buf) + len(p) + 1 <= size:
            buf = buf + "\n" + p
        else:
            chunks.append(buf)
            if len(p) > size:
                i = 0
                while i < len(p):
                    chunks.append(p[i:i + size])
                    i += size - overlap
                buf = ""
            else:
                buf = p
    if buf:
        chunks.append(buf)
    out = []
    for c in chunks:
        if out and c == out[-1]:
            continue
        out.append(c)
    return out


def add_document(kb_id, doc_id, chunks):
    """文档分块入库"""
    if not _check_available():
        raise RuntimeError("向量库组件未安装或模型缺失")
    embs = embed(chunks)
    col = _get_collection(kb_id)
    ids = [f"{doc_id}#{i}" for i in range(len(chunks))]
    col.upsert(
        ids=ids, embeddings=embs.tolist(), documents=chunks,
        metadatas=[{"doc_id": doc_id} for _ in chunks])


def delete_document(kb_id, doc_id):
    col = _get_collection(kb_id)
    col.delete(where={"doc_id": doc_id})


def delete_collection(kb_id):
    try:
        _get_client().delete_collection(name=f"kb_{kb_id}")
    except Exception:
        pass


def retrieve(kb_id, query, top_k=None):
    """检索 top_k 条最相关片段，返回 [{content, distance}]"""
    top_k = top_k or config.KB_TOP_K
    if not _check_available():
        return []
    col = _get_collection(kb_id)
    count = col.count()
    if count == 0:
        return []
    q = embed([query])
    res = col.query(query_embeddings=q.tolist(), n_results=min(top_k, count))
    docs = res.get("documents", [[]])[0]
    dists = res.get("distances", [[]])[0]
    return [{"content": d, "distance": round(float(dist), 4)} for d, dist in zip(docs, dists)]