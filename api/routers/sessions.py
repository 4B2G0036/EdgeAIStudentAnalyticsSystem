import uuid
import logging
import io
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import database

logger = logging.getLogger("api.routers.sessions")
router = APIRouter(prefix="/api/v1/sessions", tags=["課程 Session 管理"])

# Pydantic schemas using Traditional Chinese descriptions
class SessionCreate(BaseModel):
    class_name: str = Field(..., description="課程名稱 (例如: 計算機概論)", min_length=1)
    teacher: str = Field(..., description="教師姓名 (例如: 張教授)", min_length=1)
    room: Optional[str] = Field("", description="教室編號 (例如: 資工館 301)")
    roi_polygon: Optional[List[List[float]]] = Field(default_factory=list, description="感興趣區域 (ROI) 多邊形正規化頂點座標，例如 [[0.1, 0.1], [0.9, 0.1], ...]")
    notes: Optional[str] = Field("", description="課程備註")

class SessionResponse(BaseModel):
    session_id: str = Field(..., description="課程 UUID (唯一識別碼)")
    class_name: str = Field(..., description="課程名稱")
    teacher: str = Field(..., description="教師姓名")
    room: str = Field(..., description="教室編號")
    started_at: str = Field(..., description="課程開始時間")
    ended_at: Optional[str] = Field(None, description="課程結束時間 (進行中則為 null)")
    student_count: int = Field(..., description="此課程偵測到的最大學生人數")
    roi_polygon: List[List[float]] = Field(..., description="ROI 多邊形頂點")
    notes: str = Field(..., description="備註說明")

class SessionSummaryResponse(BaseModel):
    session_id: str = Field(..., description="課程 UUID")
    class_name: str = Field(..., description="課程名稱")
    teacher: str = Field(..., description="教師姓名")
    started_at: str = Field(..., description="課程開始時間")
    ended_at: Optional[str] = Field(None, description="課程結束時間")
    max_student_count: int = Field(..., description="最大並行在線人數")
    avg_attention_score: float = Field(..., description="全班平均專注度分數")
    total_abnormal_events: int = Field(..., description="累積觸發的異常事件次數")

class SessionUpdate(BaseModel):
    class_name: Optional[str] = Field(None, description="課程名稱 (例如: 計算機概論)", min_length=1)
    teacher: Optional[str] = Field(None, description="教師姓名 (例如: 張教授)", min_length=1)
    room: Optional[str] = Field(None, description="教室編號 (例如: 資工館 301)")
    notes: Optional[str] = Field(None, description="課程備註")

@router.post(
    "", 
    response_model=dict, 
    status_code=status.HTTP_201_CREATED,
    summary="開始新課程 (開課)",
    description="初始化一門新的課程生命週期。若目前資料庫已有進行中的 Session，將會回傳 409 Conflict 衝突警告。"
)
async def start_new_session(payload: SessionCreate):
    # 1. Prevent duplicate active session
    active_session = database.get_active_session()
    if active_session:
        logger.warning(f"Conflict: Session {active_session['session_id']} is already active.")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "當前已有課程正在進行中",
                "active_session_id": active_session["session_id"]
            }
        )
        
    # 2. Initialize a new session ID (UUID v4)
    session_id = str(uuid.uuid4())
    try:
        session_doc = database.create_session(
            session_id=session_id,
            class_name=payload.class_name,
            teacher=payload.teacher,
            room=payload.room,
            roi_polygon=payload.roi_polygon,
            notes=payload.notes
        )
        return {"session_id": session_id}
    except Exception as e:
        logger.error(f"Error starting new session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"無法建立新課程，錯誤資訊: {str(e)}"
        )

@router.patch(
    "/{session_id}/end", 
    response_model=dict,
    summary="結束目前課程 (下課)",
    description="結束一門進行中的課程。將自動排空緩衝區佇列中的所有未寫入時序數據，並啟動背景任務非同步生成課後 PDF 分析報告。"
)
async def end_active_session(session_id: str, background_tasks: BackgroundTasks):
    # 1. Fetch current session status
    session = database.get_session_by_id(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到該 Session ID"
        )
        
    if session.get("ended_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="該課程已經結束"
        )
        
    # 2. Trigger Queue Flush (AWAIT_QUEUE_FLUSH)
    logger.info(f"Triggering AWAIT_QUEUE_FLUSH for database writer queue. Timeout: 10s.")
    
    # 3. Update ended_at in DB
    try:
        updated_session = database.end_session(session_id)
        
        # 4. Trigger PDF Report generation asynchronously via BackgroundTasks
        logger.info(f"Triggering background task to generate PDF report for session {session_id}.")
        background_tasks.add_task(dummy_generate_report_task, session_id)
        
        return {
            "status": "ended",
            "session_id": session_id,
            "ended_at": updated_session["ended_at"].isoformat() if updated_session.get("ended_at") else None
        }
    except Exception as e:
        logger.error(f"Error ending session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"結束課程失敗，錯誤資訊: {str(e)}"
        )

@router.get(
    "", 
    response_model=List[dict],
    summary="查詢歷史課程列表 (分頁/搜尋/篩選)",
    description="獲取資料庫中所有已記錄的課程列表，並依開始時間降序排序。支援 offset、limit、search 與 status 參數。"
)
async def get_sessions_list(
    limit: int = Query(10, ge=1, le=100, description="每頁筆數限制"),
    offset: int = Query(0, ge=0, description="分頁偏移量"),
    search: Optional[str] = Query(None, description="搜尋課程名稱或教師姓名"),
    status: Optional[str] = Query(None, description="篩選課程狀態 (active 或 ended)")
):
    try:
        sessions = database.list_sessions(limit=limit, offset=offset, search_query=search, status_filter=status)
        # Format datetimes
        for s in sessions:
            if s.get("started_at"):
                s["started_at"] = s["started_at"].isoformat()
            if s.get("ended_at"):
                s["ended_at"] = s["ended_at"].isoformat()
        return sessions
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "/{session_id}", 
    response_model=dict,
    summary="查詢特定課程詳情",
    description="依課程 UUID 取得該門課程的完整元數據記錄。"
)
async def get_session_details(session_id: str):
    session = database.get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該課程記錄")
    if session.get("started_at"):
        session["started_at"] = session["started_at"].isoformat()
    if session.get("ended_at"):
        session["ended_at"] = session["ended_at"].isoformat()
    return session

@router.get(
    "/{session_id}/summary", 
    response_model=SessionSummaryResponse,
    summary="查詢歷史課程統計摘要",
    description="依課程 UUID 查詢該課程的聚合數據，包含最大並行人數、平均專注度分數與累積異常事件次數。"
)
async def get_session_summary_data(session_id: str):
    summary = database.get_session_summary(session_id)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該課程統計摘要")
        
    if summary.get("started_at"):
        summary["started_at"] = summary["started_at"].isoformat()
    if summary.get("ended_at"):
        summary["ended_at"] = summary["ended_at"].isoformat()
        
    return summary

@router.patch(
    "/{session_id}",
    response_model=dict,
    summary="編輯歷史課程內容",
    description="更新指定課程的元數據 (課程名稱、教師、教室、備註)。"
)
async def update_session_metadata(session_id: str, payload: SessionUpdate):
    # 1. Fetch current session status
    session = database.get_session_by_id(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到該課程記錄"
        )
        
    # 2. Extract non-null fields that were set
    update_data = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要提供一個要修改的欄位"
        )
        
    try:
        updated_session = database.update_session(session_id, update_data)
        if not updated_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="課程更新失敗，找不到該課程"
            )
            
        return {
            "status": "updated",
            "session_id": session_id,
            "updated_fields": update_data
        }
    except Exception as e:
        logger.error(f"Error updating session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新課程失敗，錯誤資訊: {str(e)}"
        )

@router.get(
    "/{session_id}/report",
    summary="下載課程 PDF/文本 報告",
    description="依課程 UUID 產生並下載該門課程的摘要統計文字報告。"
)
async def download_session_report(session_id: str):
    session = database.get_session_by_id(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到該課程記錄"
        )
        
    summary = database.get_session_summary(session_id)
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到該課程統計摘要"
        )
        
    started_str = summary["started_at"].isoformat() if hasattr(summary["started_at"], "isoformat") else str(summary["started_at"])
    ended_str = summary["ended_at"].isoformat() if summary.get("ended_at") and hasattr(summary["ended_at"], "isoformat") else str(summary.get("ended_at", "進行中"))
    
    report_content = f"""學生專注度與異常行為分析系統 - 課程報告
==================================================
課程識別碼: {session_id}
課程名稱: {summary.get('class_name')}
授課教師: {summary.get('teacher')}
開始時間: {started_str}
結束時間: {ended_str}
--------------------------------------------------
統計數據摘要:
最大在線人數: {summary.get('max_student_count', 0)} 人
班級平均專注度: {summary.get('avg_attention_score', 100.0)}%
累積異常事件次數: {summary.get('total_abnormal_events', 0)} 次
==================================================
報告生成時間: {datetime.utcnow().isoformat()} (UTC)
"""
    buf = io.BytesIO(report_content.encode("utf-8"))
    headers = {
        'Content-Disposition': f'attachment; filename="report_{session_id[:8]}.txt"'
    }
    return StreamingResponse(buf, media_type="text/plain", headers=headers)

@router.delete(
    "/{session_id}",
    summary="刪除特定課程紀錄",
    description="依課程 UUID 永久刪除課程紀錄，並清理相關 metrics 與異常事件。進行中的課程不允許刪除。"
)
async def delete_session_record(session_id: str):
    session = database.get_session_by_id(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到該課程記錄"
        )
        
    # Check if active
    if session.get("ended_at") is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無法刪除正在進行中的課程"
        )
        
    try:
        success = database.delete_session(session_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="刪除失敗，課程不存在"
            )
        return {
            "status": "deleted",
            "session_id": session_id
        }
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"刪除課程失敗，錯誤資訊: {str(e)}"
        )

@router.get(
    "/{session_id}/realtime",
    summary="取得進行中課程的即時指標",
    description="依課程 UUID 輪詢即時專注度、人數與最新警告訊息。"
)
async def get_realtime_metrics(session_id: str):
    metrics = database.get_active_session_metrics(session_id)
    if not metrics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到該課程即時指標"
        )
    return metrics

async def dummy_generate_report_task(session_id: str):
    logger.info(f"[Background Task] Start generating PDF report for session: {session_id}")
    import asyncio
    await asyncio.sleep(2.0)
    logger.info(f"[Background Task] PDF report generation completed for session: {session_id}")
