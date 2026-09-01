"""
RKLLM NPU WebUI - NPU 进程管理
管理 rkllm 引擎：llm_demo + .rkllm (常驻常连接)
"""

import asyncio
import os

from config import (
    MODELS, SAMPLING_PARAMS, PROMPT_SIGN,
    get_model_by_id,
)


# ---- 全局状态 ----
current_model_id = MODELS[0]["id"]
active_session_id = None
llm_process = None

llm_lock = asyncio.Lock()


def get_current_model_config() -> dict:
    return get_model_by_id(current_model_id) or MODELS[0]


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
    model_path = get_current_model_config()["path"]
    print(f"\n[*] 拉起 rkllm 引擎: {current_model_id}")
    sp = SAMPLING_PARAMS
    llm_process = await asyncio.create_subprocess_exec(
        "llm_demo", model_path, "1024", str(get_current_model_config().get("ctx_max", 4096)),
        str(sp.get("temperature", 0.8)), str(sp.get("top_p", 0.95)),
        str(sp.get("top_k", 40)), str(sp.get("repeat_penalty", 1.1)),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT, env=env)
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
