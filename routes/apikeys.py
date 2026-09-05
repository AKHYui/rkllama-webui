"""
RKLLM NPU WebUI - API-Key 管理路由
供「外部调用」（OpenAI 兼容接口 /v1）使用的 API-Key 增删查。
明文 Key 仅在创建时返回一次，此后仅存哈希。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from database import create_api_key, get_api_keys, delete_api_key
from routes.auth import require_auth

router = APIRouter(prefix="/api/apikeys", tags=["apikeys"])


class CreateApiKeyRequest(BaseModel):
    name: str = Field("", max_length=64)


@router.get("", dependencies=[Depends(require_auth)])
async def list_api_keys():
    """列出全部 API-Key（不含明文）"""
    return {"keys": get_api_keys()}


@router.post("", dependencies=[Depends(require_auth)])
async def create_key_endpoint(req: CreateApiKeyRequest):
    """创建 API-Key，明文仅在本次响应返回一次"""
    result = create_api_key(req.name)
    return {
        "status": "success",
        "id": result["id"],
        "key": result["key"],
        "prefix": result["prefix"],
        "name": result["name"],
    }


@router.delete("/{key_id}", dependencies=[Depends(require_auth)])
async def delete_key_endpoint(key_id: int):
    """删除 API-Key"""
    if delete_api_key(key_id):
        return {"status": "success"}
    return {"status": "error", "message": "Key 不存在"}
