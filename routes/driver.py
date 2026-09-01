"""
RKLLM NPU WebUI - 驱动挂载路由
配置 llm_demo 可执行文件路径（RKNN rkllm 引擎驱动）。
"""

import os
import shutil

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import npu
from database import get_setting, set_setting
from routes.auth import require_auth

router = APIRouter(prefix="/api", tags=["driver"])

DRIVER_KEY = "llm_demo_path"


class DriverRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=512)
    skip_check: bool = False


@router.get("/driver", dependencies=[Depends(require_auth)])
async def get_driver():
    """获取当前 llm_demo 路径"""
    return {"path": npu.get_llm_demo_path()}


@router.put("/driver", dependencies=[Depends(require_auth)])
async def update_driver(req: DriverRequest):
    """更新 llm_demo 路径"""
    path = req.path.strip()
    if not path:
        return {"status": "error", "message": "路径不能为空"}
    if not req.skip_check:
        found = shutil.which(path)
        if not found:
            return {"status": "error", "message": "找不到可执行文件: " + path}
        if not os.access(found, os.X_OK):
            return {"status": "error", "message": "文件存在但不可执行: " + found}
    set_setting(DRIVER_KEY, path)
    print(f"[driver] llm_demo 路径已更新: {path}")
    return {"status": "success", "path": path}