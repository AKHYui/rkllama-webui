"""RKLLM NPU WebUI - 文生图引擎（SD 子进程管理）

与 npu.py（llm_demo）对称：SD 模型运行在独立的 sd_worker 子进程，
由本模块负责拉起/通信/kill。引擎级互斥在 engine.py 中统一处理，
本模块提供在"engine_lock 已持有"前提下使用的 *locked 函数。
"""

import asyncio
import json
import os
import uuid

import config

_worker_process = None       # asyncio.subprocess.Process
_worker_ready = None         # asyncio.Event
_reader_task = None          # 后台读 stdout 任务
_pending = {}                # req_id -> asyncio.Future


def is_running():
    return _worker_process is not None and _worker_process.returncode is None


async def _check_available():
    """检查 SD 运行环境（worker 解释器 + 模型目录）"""
    if not os.path.isfile(config.SD_PYTHON):
        return False, "未找到 SD 运行环境，请运行 scripts/install_sd.sh"
    if not os.path.isdir(config.SD_MODEL_DIR) or \
            not os.path.isfile(os.path.join(config.SD_MODEL_DIR, "unet", "model.rknn")):
        return False, f"模型目录不存在: {config.SD_MODEL_DIR}"
    return True, ""


async def start_worker_locked():
    """engine_lock 已持有：拉起 sd_worker 子进程并等待就绪"""
    global _worker_process, _worker_ready, _reader_task
    if is_running():
        return
    if not os.path.isfile(config.SD_PYTHON):
        raise RuntimeError("未找到 SD 运行环境，请运行 scripts/install_sd.sh")
    if not os.path.isdir(config.SD_MODEL_DIR):
        raise RuntimeError(f"模型目录不存在: {config.SD_MODEL_DIR}")
    os.makedirs(config.SD_OUTPUT_DIR, exist_ok=True)

    _worker_ready = asyncio.Event()
    env = os.environ.copy()
    _worker_process = await asyncio.create_subprocess_exec(
        config.SD_PYTHON, config.SD_WORKER,
        "--model_dir", config.SD_MODEL_DIR,
        "--output_dir", config.SD_OUTPUT_DIR,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env)
    _reader_task = asyncio.create_task(_read_worker())
    try:
        await asyncio.wait_for(_worker_ready.wait(), timeout=config.SD_READY_TIMEOUT)
    except asyncio.TimeoutError:
        await release_sd_locked()
        raise RuntimeError("SD 引擎启动超时，请检查 sd_worker 依赖与模型文件")


async def _read_worker():
    """持续读取 worker stdout，处理 ready/result/error 事件"""
    global _worker_process
    proc = _worker_process
    if proc is None:
        return
    while True:
        try:
            line = await proc.stdout.readline()
        except Exception:
            break
        if not line:
            break
        try:
            msg = json.loads(line.decode("utf-8", errors="replace"))
        except Exception:
            continue
        ev = msg.get("event")
        if ev == "ready" and _worker_ready is not None:
            _worker_ready.set()
        elif ev == "result":
            fut = _pending.pop(msg.get("id", ""), None)
            if fut and not fut.done():
                fut.set_result(msg.get("path", ""))
        elif ev == "error":
            fut = _pending.pop(msg.get("id", ""), None)
            if fut and not fut.done():
                fut.set_exception(RuntimeError(msg.get("message", "SD 生成失败")))


async def generate_locked(prompt, negative_prompt="", steps=4, cfg=1.0, seed=-1):
    """engine_lock 已持有：向 worker 发请求并等待 PNG 路径"""
    if not is_running():
        raise RuntimeError("SD 引擎未就绪")
    req_id = uuid.uuid4().hex[:8]
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    _pending[req_id] = fut
    req = {
        "cmd": "generate", "id": req_id,
        "prompt": prompt, "negative_prompt": negative_prompt,
        "steps": int(steps), "cfg": float(cfg), "seed": int(seed),
    }
    try:
        _worker_process.stdin.write((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
        await _worker_process.stdin.drain()
        path = await asyncio.wait_for(fut, timeout=config.SD_GEN_TIMEOUT)
        if not os.path.isfile(path):
            raise RuntimeError("生成结果文件不存在: " + path)
        return path
    except asyncio.TimeoutError:
        _pending.pop(req_id, None)
        raise RuntimeError("SD 生成超时")
    except asyncio.CancelledError:
        _pending.pop(req_id, None)
        raise


async def release_sd_locked():
    """engine_lock 已持有：kill SD 子进程（内核立即归还 NPU + 内存）"""
    global _worker_process, _reader_task
    if _worker_process is not None and _worker_process.returncode is None:
        try:
            _worker_process.kill()
            await _worker_process.wait()
        except Exception:
            pass
    _worker_process = None
    _reader_task = None
    _pending.clear()
    _worker_ready = None


async def shutdown():
    """进程退出时清理"""
    if is_running():
        await release_sd_locked()