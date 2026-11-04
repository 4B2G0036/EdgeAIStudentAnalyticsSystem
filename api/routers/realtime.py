import time
import json
import asyncio
import logging
import numpy as np
import cv2
from datetime import datetime
from typing import Optional, List, Tuple
from fastapi import APIRouter, File, UploadFile, Request, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import database
from core.pose_analyzer import PoseAnalyzer
from api.persistence import get_persister

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

_prev_event_set: set = set()


def update_live_state(score: float, student_count: int, latest_event: str, events: list = None):
    global _live_state, _prev_event_set
    _live_state["attention_score"] = float(score)
    _live_state["active_student_count"] = int(student_count)
    if latest_event:
        _live_state["latest_event"] = str(latest_event)
    current = set(events or [])
    if events:
        _live_state["events"] = list(events)
        # 僅在事件「新出現」時累計；持續中的同一事件不再每幀 (5 FPS) 重複計數
        _live_state["total_abnormal_events"] += len(current - _prev_event_set)
    _prev_event_set = current
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

async def get_current_realtime_payload() -> dict:
    """Helper function to aggregate current in-memory live state and database session metrics."""
    now_iso = datetime.utcnow().isoformat()
    try:
        active_session = await asyncio.to_thread(database.get_active_session)
        is_live_fresh = (time.time() - _live_state["last_updated"]) < 10.0
        
        if not active_session:
            return {
                "is_active": False,
                "session_id": None,
                "class_name": None,
                "teacher": None,
                "attention_score": _live_state["attention_score"] if is_live_fresh else 100.0,
                "active_student_count": _live_state["active_student_count"] if is_live_fresh else 0,
                "total_abnormal_events": _live_state["total_abnormal_events"],
                "latest_event": _live_state["latest_event"] if is_live_fresh else "尚未開啟課程 (鏡頭待命)",
                "timestamp": now_iso
            }
            
        session_id = active_session["session_id"]
        live_metrics = (await asyncio.to_thread(database.get_active_session_metrics, session_id)) or {}
        
        current_score = _live_state["attention_score"] if is_live_fresh else float(live_metrics.get("attention_score", 100.0))
        current_count = _live_state["active_student_count"] if is_live_fresh else int(live_metrics.get("student_count", 0))
        current_event = _live_state["latest_event"] if is_live_fresh else live_metrics.get("latest_event", "")
        
        return {
            "is_active": True,
            "session_id": session_id,
            "class_name": active_session.get("class_name"),
            "teacher": active_session.get("teacher"),
            "attention_score": float(current_score),
            "active_student_count": int(current_count),
            # 進行中課程以資料庫去重後的事件數為準 (記憶體計數僅用於無課程時顯示，避免重複加總)
            "total_abnormal_events": int(live_metrics.get("total_abnormal_events", 0)),
            "latest_event": current_event,
            "timestamp": now_iso
        }
    except Exception as e:
        logger.error(f"Error reading realtime metrics: {e}")
        return {
            "is_active": False,
            "session_id": None,
            "class_name": None,
            "teacher": None,
            "attention_score": 100.0,
            "active_student_count": 0,
            "total_abnormal_events": 0,
            "latest_event": f"讀取異常: {str(e)}",
            "timestamp": now_iso
        }


@router.get(
    "/realtime",
    response_model=RealtimeMetricsResponse,
    summary="取得當前全班即時監控指標 (儀表板輪詢)",
    description="供儀表板每 3 秒輪詢獲取當前進行中 Session 或實時鏡頭之即時專注度、學生人數與最新告警。"
)
async def get_global_realtime_metrics():
    payload = await get_current_realtime_payload()
    return RealtimeMetricsResponse(**payload)


@router.get(
    "/realtime/sse",
    summary="實時專注度與警報 SSE 串流 (Server-Sent Events)",
    description="瀏覽器使用 EventSource 連線，伺服器主動推送最新專注度、在線人數與即時異常告警，附帶心跳保活。"
)
async def realtime_sse_stream(request: Request):
    async def event_generator():
        last_sent_score = None
        last_sent_count = None
        last_sent_event = None
        last_heartbeat = time.time()
        
        while True:
            if await request.is_disconnected():
                logger.info("SSE client disconnected.")
                break
                
            now = time.time()
            data = await get_current_realtime_payload()
            
            has_changed = (
                data["attention_score"] != last_sent_score or
                data["active_student_count"] != last_sent_count or
                data["latest_event"] != last_sent_event or
                (now - last_heartbeat) >= 2.0
            )
            
            if has_changed:
                last_sent_score = data["attention_score"]
                last_sent_count = data["active_student_count"]
                last_sent_event = data["latest_event"]
                last_heartbeat = now
                payload_json = json.dumps(data, ensure_ascii=False)
                yield f"data: {payload_json}\n\n"
            elif (now - last_heartbeat) >= 15.0:
                last_heartbeat = now
                yield ": keepalive\n\n"
                
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.websocket("/ws/realtime")
async def websocket_realtime_endpoint(websocket: WebSocket):
    """WebSocket 双向即時專注度與異常警報通訊端點。"""
    await websocket.accept()
    logger.info("WebSocket client connected to /api/v1/ws/realtime")
    last_sent_score = None
    last_sent_count = None
    last_sent_event = None
    last_push = time.time()
    
    try:
        while True:
            now = time.time()
            data = await get_current_realtime_payload()
            
            has_changed = (
                data["attention_score"] != last_sent_score or
                data["active_student_count"] != last_sent_count or
                data["latest_event"] != last_sent_event or
                (now - last_push) >= 2.0
            )
            
            if has_changed:
                last_sent_score = data["attention_score"]
                last_sent_count = data["active_student_count"]
                last_sent_event = data["latest_event"]
                last_push = now
                await websocket.send_json(data)
                
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                if msg == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected from /api/v1/ws/realtime")
    except Exception as e:
        logger.warning(f"WebSocket connection closed: {e}")


def _process_webcam_frame_sync(body: bytes) -> Tuple[Optional[dict], Optional[str]]:
    """CPU-bound and DB synchronous worker function executed in worker threadpool."""
    nparr = np.frombuffer(body, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        return None, "Cannot decode image"

    # Run AI Pose & Attention Analyzer
    analyzer = PoseAnalyzer.get_instance()
    analysis = analyzer.analyze_frame(frame, draw_overlay=False)

    score = analysis["attention_score"]
    count = analysis["student_count"]
    latest_event = analysis["latest_event"]
    events = analysis["events"]

    # Update in-memory state
    update_live_state(score, count, latest_event, events)

    # If a session is active, write to MongoDB (shared lifecycle-aware persister)
    get_persister().persist(score, count, events)

    return {
        "status": "ok",
        "student_count": count,
        "attention_score": score,
        "latest_event": latest_event,
        "events": events
    }, None


@router.post(
    "/realtime/frame",
    summary="接收前端 WebCam 影格進行 AI 推論分析",
    description="瀏覽器 WebCam 每 800ms 發送一幀 JPEG 畫面，後端執行 YOLOv8-Pose 推論並即時回傳姿態分析與專注度。"
)
async def analyze_webcam_frame(request: Request):
    try:
        # Read raw image bytes asynchronously from network
        body = await request.body()
        if not body or len(body) < 100:
            raise HTTPException(status_code=400, detail="Empty image data")

        # Offload image decoding, YOLOv8-Pose inference, and DB writes to worker thread
        # This prevents blocking the asyncio event loop during heavy CPU inference
        result, error_msg = await asyncio.to_thread(_process_webcam_frame_sync, body)
        if error_msg:
            raise HTTPException(status_code=400, detail=error_msg)

        return result
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
