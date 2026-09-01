"""
RKLLM NPU WebUI - 全局配置
管理所有可配置常量：模型列表、采样参数、默认系统提示词等。
"""

import os

# ================= 模型列表 =================
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
        "path": "/opt/models/Qwen3-4B/Qwen3-4B-rk3588-w8a8-opt-1-hybrid-ratio-1.0.rkllm",
        "engine": "rkllm",
    },
    {
        "id": "qwen3-1.7b",
        "name": "Qwen3 1.7B",
        "path": "/opt/models/Qwen3-1.7B/Qwen3-1.7B-w8a8-rk3588.rkllm",
        "engine": "rkllm",
    },
    {
        "id": "Qwen2.5-0.5b",
        "name": "Qwen2.5 0.5B",
        "path": "/opt/models/Qwen2.5-0.5B/Qwen2.5-0.5B-Instruct-1.2.0.rkllm",
        "engine": "rkllm",
    },
    {
        "id": "Deepseek-1.5b",
        "name": "Deepseek 1.5B",
        "path": "/opt/models/Deepseek-R1-1.5b/DeepSeek-R1-Distill-Qwen-1.5B-rk3588-w8a8-opt-1-hybrid-ratio-0.0.rkllm",
        "engine": "rkllm",
    },
]

# ================= 默认系统提示词 =================
DEFAULT_SYSTEM_PROMPT = """你是一个真诚、自然、有温度的聊天伙伴。你的回答应该像朋友间的对话——有主见、有态度、敢表达真实想法，不迎合、不说教、不刻意讨好。保持对话的流动感，适当使用口语化表达，让对话生动自然。"""

# ================= 采样参数配置 =================
# top_k=1 表示关闭 top_k 限制，让模型有完整的词汇选择空间
SAMPLING_PARAMS = {
    "temperature": 0.85,
    "top_p": 0.9,
    "top_k": 1,
    "repeat_penalty": 1.05
}

# ================= 其他常量 =================
PROMPT_SIGN = "user:"
DB_FILE = "chat_history.db"
SESSION_SECRET_FILE="/opt/rkllama/.session_secret"

# ================= 知识库 (RAG) =================
KB_CHUNK_SIZE = 400
KB_CHUNK_OVERLAP = 100
KB_TOP_K = 3
KB_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

if os.name == "nt":
    # 开发机(Windows) 回退到本地目录，便于界面开发
    _base = os.path.dirname(os.path.abspath(__file__))
    EMBED_MODEL_DIR = os.path.join(_base, "models", "bge-small-zh-onnx")
    CHROMA_DIR = os.path.join(_base, "chroma_db")
else:
    # 开发板 (RK3588 /opt/rkllama)
    EMBED_MODEL_DIR = "/opt/rkllama/models/bge-small-zh-onnx"
    CHROMA_DIR = "/opt/rkllama/chroma_db"


def get_model_by_id(model_id):
    for m in MODELS:
        if m["id"] == model_id:
            return m
    return None

