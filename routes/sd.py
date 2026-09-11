"""RKLLM NPU WebUI - 文生图路由

顶栏"文生图"模式调用：同步生成（36-60s），返回 PNG。
鉴权与 WebUI 一致（require_auth）。
"""

import os

from fastapi import APIRouter, Depends
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

import engine
from routes.auth import require_auth

router = APIRouter(prefix="/api/sd", tags=["sd"])


class SDGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)
    negative_prompt: str = Field("", max_length=1000)
    steps: int = Field(4, ge=1, le=8)
    cfg: float = Field(1.0, ge=1.0, le=4.0)
    seed: int = Field(-1, ge=-1)


@router.get("/status", dependencies=[Depends(require_auth)])
async def sd_status():
    return await engine.status()


@router.post("/generate", dependencies=[Depends(require_auth)])
async def sd_generate(req: SDGenerateRequest):
    st = await engine.status()
    if not st["available"]:
        return JSONResponse(status_code=400,
                            content={"status": "error", "message": st["message"]})
    try:
        path = await engine.generate_image(
            req.prompt, req.negative_prompt, req.steps, req.cfg, req.seed)
        with open(path, "rb") as f:
            data = f.read()
        try:
            os.remove(path)
        except OSError:
            pass
        return Response(data, media_type="image/png")
    except Exception as e:
        return JSONResponse(status_code=500,
                            content={"status": "error", "message": str(e)})