"""
api/routers/system.py
======================
系統與對外連線狀態 API 路由：
  - GET /api/v1/system/tunnel: 查詢當前 API 對外穿透網址 (Tunnel URL) 與狀態
"""

import os
import json
import logging
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("api.routers.system")
router = APIRouter(prefix="/api/v1/system", tags=["系統與連線狀態"])

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATUS_FILE = os.path.join(ROOT_DIR, "scratch", "tunnel_status.json")


class TunnelStatusResponse(BaseModel):
    status: str = Field(..., description="穿透通道狀態 (online / offline / unknown)")
    tunnel_url: Optional[str] = Field(None, description="HTTPS 對外穿透網址")
    swagger_docs: Optional[str] = Field(None, description="對外 Swagger API 文件網址")
    dashboard_url: Optional[str] = Field(None, description="對外 Web 儀表板網址")
    engine: Optional[str] = Field(None, description="穿透引擎 (Cloudflare Tunnel / Pinggy SSH 等)")
    updated_at: Optional[str] = Field(None, description="最後更新時間")


@router.get("/tunnel", response_model=TunnelStatusResponse, summary="查詢當前 API 對外穿透網址狀態")
def get_tunnel_status():
    """
    獲取當前本機 API 服務自動生成的 HTTPS 對外穿透網址。
    供前端 Dashboard、靜態 Web App 或第三方 Client 動態取得公網端點。
    """
    if not os.path.exists(STATUS_FILE):
        env_public = os.getenv("PUBLIC_API_URL")
        if env_public:
            return TunnelStatusResponse(
                status="online",
                tunnel_url=env_public,
                swagger_docs=f"{env_public}/docs",
                dashboard_url=f"{env_public}/dashboard/",
                engine="environment_variable",
                updated_at=None
            )
        return TunnelStatusResponse(
            status="offline",
            tunnel_url=None,
            swagger_docs=None,
            dashboard_url=None,
            engine=None,
            updated_at=None
        )

    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return TunnelStatusResponse(
            status=data.get("status", "unknown"),
            tunnel_url=data.get("tunnel_url"),
            swagger_docs=data.get("swagger_docs"),
            dashboard_url=data.get("dashboard_url"),
            engine=data.get("engine"),
            updated_at=data.get("updated_at")
        )
    except Exception as e:
        logger.error(f"Failed to read tunnel status file: {e}")
        return TunnelStatusResponse(
            status="error",
            tunnel_url=None,
            swagger_docs=None,
            dashboard_url=None,
            engine=None,
            updated_at=None
        )
