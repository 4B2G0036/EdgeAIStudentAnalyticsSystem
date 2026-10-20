import time
import logging
import numpy as np
import cv2
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, File, UploadFile, Request, HTTPException, status
from pydantic import BaseModel, Field

import database
from core.pose_analyzer import PoseAnalyzer

logger = logging.getLogger("api.routers.realtime")
router = APIRouter(prefix="/api/v1", tags=["即時指標與狀態監控"])

# Global in-memory cache of live AI inference metrics
_live_state = {
    "attention_score": 100.0,
    "active_student_count": 0,
    "total_abnormal_events": 0,
    "latest_event": "🟢 鏡頭待命就緒",
    "events": [],
    "last_updated": 0.0
}

def update_live_state(score: float, student_count: int, latest_event: str, events: list = None):
    global _live_state
    _live_state["attention_score"] = float(score)
    _live_state["active_student_count"] = int(student_count)
    if latest_event:
        _live_state["latest_event"] = str(latest_event)
    if events:
        _live_state["events"] = list(events)
        _live_state["total_abnormal_events"] += len(events)
    _live_state["last_updated"] = time.time()

def get_current_live_state():
    return _live_state

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
    description="供儀表板每 3 秒輪詢獲取當前進行中 Session 或實時鏡頭之即時專注度、學生人數與最新告警。"
)
async def get_global_realtime_metrics():
    now_iso = datetime.utcnow().isoformat()
    try:
        active_session = database.get_active_session()
        
        # Check if we have recent live AI inference in memory
        is_live_fresh = (time.time() - _live_state["last_updated"]) < 10.0
        
        if not active_session:
            # Even when no session is formally created, return live camera analytics
            return RealtimeMetricsResponse(
                is_active=False,
                session_id=None,
                class_name=None,
                teacher=None,
                attention_score=_live_state["attention_score"] if is_live_fresh else 100.0,
                active_student_count=_live_state["active_student_count"] if is_live_fresh else 0,
                total_abnormal_events=_live_state["total_abnormal_events"],
                latest_event=_live_state["latest_event"] if is_live_fresh else "尚未開啟課程 (鏡頭待命)",
                timestamp=now_iso
            )
            
        session_id = active_session["session_id"]
        live_metrics = database.get_active_session_metrics(session_id) or {}
        
        # Blend in-memory live inference if available
        current_score = _live_state["attention_score"] if is_live_fresh else float(live_metrics.get("attention_score", 100.0))
        current_count = _live_state["active_student_count"] if is_live_fresh else int(live_metrics.get("student_count", 0))
        current_event = _live_state["latest_event"] if is_live_fresh else live_metrics.get("latest_event", "")
        
        return RealtimeMetricsResponse(
            is_active=True,
            session_id=session_id,
            class_name=active_session.get("class_name"),
            teacher=active_session.get("teacher"),
            attention_score=float(current_score),
            active_student_count=int(current_count),
            total_abnormal_events=int(live_metrics.get("total_abnormal_events", 0)) + _live_state["total_abnormal_events"],
            latest_event=current_event,
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

@router.post(
    "/realtime/frame",
    summary="接收前端 WebCam 影格進行 AI 推論分析",
    description="瀏覽器 WebCam 每 800ms 發送一幀 JPEG 畫面，後端執行 YOLOv8-Pose 推論並即時回傳姿態分析與專注度。"
)
async def analyze_webcam_frame(request: Request):
    try:
        # Read raw image bytes
        body = await request.body()
        if not body or len(body) < 100:
            raise HTTPException(status_code=400, detail="Empty image data")
            
        nparr = np.frombuffer(body, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            raise HTTPException(status_code=400, detail="Cannot decode image")

        # Run AI Pose & Attention Analyzer
        analyzer = PoseAnalyzer.get_instance()
        analysis = analyzer.analyze_frame(frame, draw_overlay=False)

        score = analysis["attention_score"]
        count = analysis["student_count"]
        latest_event = analysis["latest_event"]
        events = analysis["events"]

        # Update in-memory state
        update_live_state(score, count, latest_event, events)

        # If a session is active, write to MongoDB
        active_session = database.get_active_session()
        if active_session:
            sid = active_session["session_id"]
            if count > 0:
                database.write_attention_metric(sid, score, count)
            for ev in events:
                # ev format: "S001: 疑似使用手機 (PHONE_SUSPECTED)"
                parts = ev.split(":", 1)
                student_id = parts[0].strip()
                event_type = parts[1].strip() if len(parts) > 1 else "abnormal"
                database.write_abnormal_event(sid, student_id, event_type)

        return {
            "status": "ok",
            "student_count": count,
            "attention_score": score,
            "latest_event": latest_event,
            "events": events
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing webcam frame: {e}")
        return {
            "status": "error",
            "student_count": _live_state["active_student_count"],
            "attention_score": _live_state["attention_score"],
            "latest_event": f"推論錯誤: {str(e)}",
            "events": []
        }
