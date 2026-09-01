"""
RKLLM NPU WebUI - 模型管理路由
模型列表、切换模型、采样参数、重置 NPU。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional

import config
import npu
from routes.auth import require_auth

router = APIRouter(prefix="/api", tags=["models"])


class SwitchModelRequest(BaseModel):
    model_id: str


class SamplingUpdateRequest(BaseModel):
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description='温度参数 0.0-2.0')
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description='核采样 0.0-1.0')
    top_k: Optional[int] = Field(None, ge=0, le=200, description='top-k 采样 0-200')
    repeat_penalty: Optional[float] = Field(None, ge=0.5, le=2.0, description='重复惩罚 0.5-2.0')


@router.get("/models", dependencies=[Depends(require_auth)])
async def get_models():
    """获取可用模型列表及当前模型"""
    return {"models": config.MODELS, "current": npu.current_model_id}


@router.post("/switch", dependencies=[Depends(require_auth)])
async def switch_model_endpoint(req: SwitchModelRequest):
    """切换模型并拉起 rkllm 引擎"""
    model = config.get_model_by_id(req.model_id)
    if not model:
        return {"status": "error", "message": "model not found"}

    npu.current_model_id = req.model_id
    await npu.start_llm()
    return {"status": "success", "message": f"switched to {req.model_id}"}


@router.post("/npu/restart", dependencies=[Depends(require_auth)])
async def restart_npu():
    """强制重启 NPU 进程"""
    await npu.start_llm()
    return {"status": "success", "message": "NPU restarted"}


@router.get("/sampling", dependencies=[Depends(require_auth)])
async def get_sampling():
    """获取当前采样参数"""
    return {"sampling": config.SAMPLING_PARAMS}


@router.post("/sampling", dependencies=[Depends(require_auth)])
async def update_sampling(req: SamplingUpdateRequest):
    """更新采样参数并重启 NPU"""
    if req.temperature is not None:
        config.SAMPLING_PARAMS["temperature"] = req.temperature
    if req.top_p is not None:
        config.SAMPLING_PARAMS["top_p"] = req.top_p
    if req.top_k is not None:
        config.SAMPLING_PARAMS["top_k"] = req.top_k
    if req.repeat_penalty is not None:
        config.SAMPLING_PARAMS["repeat_penalty"] = req.repeat_penalty

    await npu.start_llm()
    return {
        "status": "success",
        "message": "sampling updated",
        "sampling": config.SAMPLING_PARAMS,
    }

