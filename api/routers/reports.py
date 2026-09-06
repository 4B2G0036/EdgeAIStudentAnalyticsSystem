import io
import time
import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, List
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import StreamingResponse

import config
import database

logger = logging.getLogger("api.routers.reports")
router = APIRouter(prefix="/api/v1", tags=["課後分析報告生成"])

# Simple Client IP Rate Limiter
class SimpleRateLimiter:
    def __init__(self, limit_str: str = "5/minute"):
        try:
            parts = limit_str.split("/")
            self.max_requests = int(parts[0])
            unit = parts[1].lower()
            if "min" in unit:
                self.window_seconds = 60
            elif "sec" in unit:
                self.window_seconds = 1
            elif "hour" in unit:
                self.window_seconds = 3600
            else:
                self.window_seconds = 60
        except Exception:
            self.max_requests = 5
            self.window_seconds = 60
            
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def check_rate_limit(self, client_ip: str):
        now = time.time()
        # Filter out timestamps outside current sliding window
        valid_ts = [ts for ts in self.requests[client_ip] if now - ts < self.window_seconds]
        self.requests[client_ip] = valid_ts
        
        if len(valid_ts) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - valid_ts[0]))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"請求過於頻繁，超出速率限制 ({self.max_requests} 次 / 分鐘)。請在 {retry_after} 秒後再試。",
                headers={"Retry-After": str(retry_after)}
            )
        self.requests[client_ip].append(now)

rate_limiter = SimpleRateLimiter(config.API_RATE_LIMIT)

@router.get(
    "/report/{session_id}",
    summary="產生並下載課程 PDF / 摘要報告 (受速率限制)",
    description=f"依據課程 UUID 生成課後 PDF/文本 統計報告。受 API 速率限制 ({config.API_RATE_LIMIT}) 保護。"
)
async def generate_and_download_report(session_id: str, request: Request):
    # 1. Enforce Rate Limiting
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_limiter.check_rate_limit(client_ip)
    
    # 2. Check session existence
    session = database.get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該課程記錄")
        
    summary = database.get_session_summary(session_id)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該課程統計摘要")

    started_str = summary["started_at"].isoformat() if hasattr(summary["started_at"], "isoformat") else str(summary["started_at"])
    ended_str = summary["ended_at"].isoformat() if summary.get("ended_at") and hasattr(summary["ended_at"], "isoformat") else str(summary.get("ended_at", "進行中"))

    # Check if reportlab is available to build real PDF
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=letter)
        c.setTitle(f"Student Analytics Report - {session_id[:8]}")
        
        # Header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 750, "Student Analytics & Attention Report")
        c.setFont("Helvetica", 10)
        c.drawString(50, 735, f"Report ID: {session_id}")
        c.line(50, 725, 550, 725)
        
        # Metadata
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, 695, f"Class Name: {summary.get('class_name')}")
        c.drawString(50, 675, f"Teacher: {summary.get('teacher')}")
        c.setFont("Helvetica", 10)
        c.drawString(50, 655, f"Started At: {started_str}")
        c.drawString(50, 640, f"Ended At: {ended_str}")
        
        # Summary Box
        c.rect(50, 520, 500, 100)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(60, 595, "Executive Summary Metrics:")
        c.setFont("Helvetica", 11)
        c.drawString(70, 575, f"- Peak Student Count: {summary.get('max_student_count', 0)} students")
        c.drawString(70, 555, f"- Class Average Attention Score: {summary.get('avg_attention_score', 100.0)}%")
        c.drawString(70, 535, f"- Total Abnormal Events Recorded: {summary.get('total_abnormal_events', 0)}")
        
        # Footer
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(50, 50, f"Generated automatically by Student Analytics Edge AI Engine at {datetime.utcnow().isoformat()} UTC")
        
        c.showPage()
        c.save()
        pdf_buffer.seek(0)
        
        headers = {
            'Content-Disposition': f'attachment; filename="report_{session_id[:8]}.pdf"'
        }
        return StreamingResponse(pdf_buffer, media_type="application/pdf", headers=headers)
        
    except ImportError:
        # Fallback to Text report if reportlab is not installed
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
        return StreamingResponse(buf, media_type="text/plain; charset=utf-8", headers=headers)
