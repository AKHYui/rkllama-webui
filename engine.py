"""RKLLM NPU WebUI - 引擎互斥核心

语言模型（llm_demo 子进程）与文生图（sd_worker 子进程）共享同一块
NPU/内存，二者永远不同时运行。所有引擎切换都必须经过本模块：

  - 聊天/模型切换 → engine.ensure_llm()    （先 kill SD，再拉起/重启 LLM）
  - 文生图生成   → engine.ensure_sd()        （先 kill LLM，再拉起 SD worker）
  - 全部操作持有 engine_lock 全局串行
"""

import asyncio

import config
import npu
import sd

engine_lock = asyncio.Lock()


def mode():
    """返回当前引擎模式: llm / sd / idle"""
    if sd.is_running():
        return "sd"
    if npu.llm_process is not None and npu.llm_process.returncode is None:
        return "llm"
    return "idle"


# ============================================================
#  LLM 侧
# ============================================================

async def ensure_llm_locked(restart=False):
    """engine_lock 已持有：确保 LLM 引擎就绪（先释放 SD）。"""
    await sd.release_sd_locked()
    need = (restart or npu.llm_process is None
            or npu.llm_process.returncode is not None)
    if need:
        await npu.start_llm()


async def ensure_llm(restart=False):
    async with engine_lock:
        await ensure_llm_locked(restart)


async def restart_llm():
    """强制重启 LLM（模型切换 / 采样修改 / 手动重启）"""
    await ensure_llm(restart=True)


# ============================================================
#  文生图 (SD) 侧
# ============================================================

async def ensure_sd_locked():
    """engine_lock 已持有：确保 SD 引擎就绪（先 kill LLM 立即归还 NPU）。"""
    if npu.llm_process is not None:
        await npu.kill_llm()
    await sd.start_worker_locked()


async def ensure_sd():
    async with engine_lock:
        await ensure_sd_locked()


async def generate_image(prompt, negative_prompt="", steps=4, cfg=1.0, seed=-1):
    """同步生成一张图：切引擎 -> 生成 -> 返回 PNG 文件路径"""
    async with engine_lock:
        await ensure_sd_locked()
        return await sd.generate_locked(prompt, negative_prompt, steps, cfg, seed)


async def release_sd():
    """释放 SD 引擎（回到 idle；下次 LLM 调用会自动处理）"""
    async with engine_lock:
        await sd.release_sd_locked()


async def status():
    """供 /api/sd/status 与前端使用"""
    avail, msg = await sd._check_available()
    return {"mode": mode(), "available": avail, "message": msg}