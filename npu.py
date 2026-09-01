"""
RKLLM NPU WebUI - NPU 进程管理
管理 rkllm 引擎：llm_demo + .rkllm (常驻常连接)
"""

import asyncio
import os

from config import (
    SAMPLING_PARAMS, PROMPT_SIGN,
)
from database import get_models, get_model_by_id, get_setting


# ---- 全局状态 ----
def _default_model_id():
    models = get_models()
    return models[0]["model_id"] if models else None

current_model_id = _default_model_id() or "qwen3.5-4b-abliterated-16k"
active_session_id = None
llm_process = None

llm_lock = asyncio.Lock()


def get_llm_demo_path():
    """获取 llm_demo 可执行文件路径（可在"驱动挂载"中配置）"""
    return get_setting("llm_demo_path", "llm_demo") or "llm_demo"


def get_current_model_config() -> dict:
    return get_model_by_id(current_model_id) or (get_models()[0] if get_models() else {})


# ============================================================
#  清理
# ============================================================

async def kill_llm():
    global llm_process, active_session_id

    if llm_process is not None:
        try:
            llm_process.kill()
            await llm_process.wait()
        except Exception:
            pass
        llm_process = None
        active_session_id = None


# ============================================================
#  rkllm 引擎
# ============================================================

async def start_llm():
    global llm_process
    await kill_llm()
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = "/usr/local/lib/rkllm:" + env.get("LD_LIBRARY_PATH", "")
    cfg = get_current_model_config()
    model_path = cfg.get("path")
    if not model_path:
        print("[*] 没有可用的模型配置，跳过引擎启动")
        return False
    max_tokens = cfg.get("max_tokens", 1024)
    ctx_max = cfg.get("ctx_max", 4096)
    print(f"\n[*] 拉起 rkllm 引擎: {current_model_id} (ctx={ctx_max}, max_tokens={max_tokens})")
    sp = SAMPLING_PARAMS
    llm_demo_path = get_llm_demo_path()
    try:
        llm_process = await asyncio.create_subprocess_exec(
            llm_demo_path, model_path, str(max_tokens), str(ctx_max),
            str(sp.get("temperature", 0.8)), str(sp.get("top_p", 0.95)),
            str(sp.get("top_k", 40)), str(sp.get("repeat_penalty", 1.1)),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, env=env)
    except FileNotFoundError:
        print(f"[!] 找不到可执行程序 {llm_demo_path}，请确认 rkllm 工具链已安装，或在设置->驱动挂载中配置正确路径")
        return False
    byte_buffer = b""
    full_log = ""
    while True:
        try:
            char_byte = await llm_process.stdout.read(1)
            if not char_byte: return False
            byte_buffer += char_byte
            try:
                text = byte_buffer.decode("utf-8")
                full_log += text; byte_buffer = b""
                if full_log.endswith(PROMPT_SIGN):
                    return True
            except UnicodeDecodeError: continue
        except Exception: return False
