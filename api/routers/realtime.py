import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

import database

logger = logging.getLogger("api.routers.realtime")
router = APIRouter(prefix="/api/v1", tags=["即時指標與狀態監控"])

class RealtimeMetricsResponse(BaseModel):
    is_active: bool = Field(..., description="是否已有正在進行中的課程")
    session_id: Optional[str] = Field(None, description="進行中課程 ID")
    class_name: Optional[str] = Field(None, description="進行中課程名稱")
    teacher: Optional[str] = Field(None, description="授課教師")
    attention_score: float = Field(100.0, description="目前全班即時平均專注度 (0-100)")
    active_student_count: int = Field(0, description="目前偵測到的在線學生人數")
    total_abnormal_events: int = Field(0, description="累積觸發的異常事件次數")
    latest_event: str = Field("", description="最新觸發之異常告警描述")
    timestamp: str = Field(..., description="指標數據時間戳記 (ISO 8601)")

@router.get(
    "/realtime",
    response_model=RealtimeMetricsResponse,
    summary="取得當前全班即時監控指標 (儀表板輪詢)",
    description="供 Streamlit 儀表板每秒輪詢獲取當前進行中 Session 之即時專注度、學生人數與最新告警。"
)
async def get_global_realtime_metrics():
    now_iso = datetime.utcnow().isoformat()
    try:
        active_session = database.get_active_session()
        if not active_session:
            return RealtimeMetricsResponse(
                is_active=False,
                session_id=None,
                class_name=None,
                teacher=None,
                attention_score=100.0,
                active_student_count=0,
                total_abnormal_events=0,
                latest_event="尚未開啟課程",
                timestamp=now_iso
            )
            
        session_id = active_session["session_id"]
        live_metrics = database.get_active_session_metrics(session_id) or {}
        
        return RealtimeMetricsResponse(
            is_active=True,
            session_id=session_id,
            class_name=active_session.get("class_name"),
            teacher=active_session.get("teacher"),
            attention_score=float(live_metrics.get("attention_score", 100.0)),
            active_student_count=int(live_metrics.get("student_count", 0)),
            total_abnormal_events=int(live_metrics.get("total_abnormal_events", 0)),
            latest_event=live_metrics.get("latest_event", ""),
            timestamp=now_iso
        )
    except Exception as e:
        logger.error(f"Error serving realtime metrics endpoint: {e}")
        return RealtimeMetricsResponse(
            is_active=False,
            session_id=None,
            class_name=None,
            teacher=None,
            attention_score=100.0,
            active_student_count=0,
            total_abnormal_events=0,
            latest_event=f"讀取異常: {str(e)}",
            timestamp=now_iso
        )
