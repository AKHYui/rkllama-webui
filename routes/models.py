"""
RKLLM NPU WebUI - 模型管理路由
模型列表、模型挂载(增删改)、切换模型、采样参数、重置 NPU。
"""

import os
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional

import config
import npu
from database import (
    get_models, get_model_by_id, model_id_exists,
    add_model, update_model, delete_model,
)
from routes.auth import require_auth

router = APIRouter(prefix="/api", tags=["models"])

ENGINES = ("rkllm", "llama")
CTX_MAX_LIMIT = 16384


class SwitchModelRequest(BaseModel):
    model_id: str


class SamplingUpdateRequest(BaseModel):
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description='温度参数 0.0-2.0')
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description='核采样 0.0-1.0')
    top_k: Optional[int] = Field(None, ge=0, le=200, description='top-k 采样 0-200')
    repeat_penalty: Optional[float] = Field(None, ge=0.5, le=2.0, description='重复惩罚 0.5-2.0')


class ModelMountRequest(BaseModel):
    model_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=50)
    path: str = Field(..., min_length=1, max_length=512)
    ctx_max: int = Field(..., ge=1, le=CTX_MAX_LIMIT)
    max_tokens: int = Field(..., ge=1, le=CTX_MAX_LIMIT)
    engine: str = Field("rkllm", max_length=16)
    temperature: Optional[float] = Field(None, ge=0.1, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    repeat_penalty: Optional[float] = Field(None, ge=1.0, le=2.0)
    skip_check: bool = False


def _validate_model(req) -> Optional[str]:
    """返回错误信息；合法返回 None"""
    if not re.match(r"^[A-Za-z0-9._-]+$", req.model_id):
        return "模型标识只能包含字母、数字、点、下划线、连字符"
    if req.engine not in ENGINES:
        return "未知的引擎类型"
    if req.max_tokens > req.ctx_max:
        return "单次回复量不能超过总上下文"
    if not req.skip_check and not os.path.exists(req.path):
        return "模型文件不存在: " + req.path
    return None


@router.get("/models", dependencies=[Depends(require_auth)])
async def get_models_endpoint():
    """获取已挂载模型列表及当前模型"""
    return {"models": get_models(), "current": npu.current_model_id}


@router.post("/models", dependencies=[Depends(require_auth)])
async def create_model(req: ModelMountRequest):
    """挂载新模型"""
    if model_id_exists(req.model_id):
        return {"status": "error", "message": f"模型标识 {req.model_id} 已存在"}
    err = _validate_model(req)
    if err:
        return {"status": "error", "message": err}
    return add_model(req.model_dump())


@router.put("/models/{model_id}", dependencies=[Depends(require_auth)])
async def update_model_endpoint(model_id: str, req: ModelMountRequest):
    """修改已挂载模型（标识不可修改）"""
    if not get_model_by_id(model_id):
        return {"status": "error", "message": "模型不存在"}
    err = _validate_model(req)
    if err:
        return {"status": "error", "message": err}
    return update_model(model_id, req.model_dump())


@router.delete("/models/{model_id}", dependencies=[Depends(require_auth)])
async def delete_model_endpoint(model_id: str):
    """卸载模型（当前使用的模型不可删除）"""
    if model_id == npu.current_model_id:
        return {"status": "error", "message": "当前正在使用的模型不能删除，请先切换到其他模型"}
    if not get_model_by_id(model_id):
        return {"status": "error", "message": "模型不存在"}
    return delete_model(model_id)


@router.post("/switch", dependencies=[Depends(require_auth)])
async def switch_model_endpoint(req: SwitchModelRequest):
    """切换模型并拉起 rkllm 引擎"""
    model = get_model_by_id(req.model_id)
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


@router.post("/reset", dependencies=[Depends(require_auth)])
async def reset_npu_alias():
    """旧前端兼容别名：/api/reset 等价于 /api/npu/restart"""
    await npu.start_llm()
    return {"status": "success", "message": "NPU 进程已重置，内存已清空"}


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