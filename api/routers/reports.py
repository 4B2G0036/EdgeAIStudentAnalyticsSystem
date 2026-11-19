import os
import io
import time
import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from fastapi import APIRouter, Request, Query, HTTPException, status
from fastapi.responses import StreamingResponse

import config
import database
from core.drawing import find_cjk_font_path

logger = logging.getLogger("api.routers.reports")
router = APIRouter(prefix="/api/v1", tags=["課後分析報告生成"])

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORTS_CACHE_DIR = os.path.join(ROOT_DIR, "scratch", "reports")
os.makedirs(REPORTS_CACHE_DIR, exist_ok=True)

_TZ_TAIPEI = timezone(timedelta(hours=8))
_PDF_FONT_REGISTERED: Optional[str] = None


def _get_pdf_font_name() -> str:
    """Register and return a Traditional Chinese / CJK TrueType font for ReportLab."""
    global _PDF_FONT_REGISTERED
    if _PDF_FONT_REGISTERED:
        return _PDF_FONT_REGISTERED

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        candidates = []
        cjk_path = find_cjk_font_path()
        if cjk_path:
            candidates.append(cjk_path)
        candidates.extend([
            r"C:\Windows\Fonts\msjh.ttc",
            r"C:\Windows\Fonts\msjhbd.ttc",
            r"C:\Windows\Fonts\mingliu.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        ])

        for path in candidates:
            if path and os.path.isfile(path):
                try:
                    if path.lower().endswith(".ttc"):
                        pdfmetrics.registerFont(TTFont("CJKFont", path, subfontIndex=0))
                    else:
                        pdfmetrics.registerFont(TTFont("CJKFont", path))
                    _PDF_FONT_REGISTERED = "CJKFont"
                    return _PDF_FONT_REGISTERED
                except Exception as exc:
                    logger.debug(f"Failed to register CJK font {path}: {exc}")
    except Exception as exc:
        logger.warning(f"ReportLab TTFont registration unavailable: {exc}")

    _PDF_FONT_REGISTERED = "Helvetica"
    return _PDF_FONT_REGISTERED


def _format_taipei_dt(val) -> str:
    """Format a UTC datetime or ISO string into Asia/Taipei YYYY-MM-DD HH:MM:SS."""
    if not val:
        return "進行中"
    try:
        if isinstance(val, str):
            s = val.strip()
            if s in ("進行中", "已結束"):
                return s
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        elif isinstance(val, datetime):
            dt = val
        else:
            return str(val)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(_TZ_TAIPEI)
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(val)


def _format_duration_str(started_at, ended_at) -> str:
    """Compute human-readable duration string between started_at and ended_at."""
    try:
        if not started_at:
            return "—"
        s = started_at if isinstance(started_at, datetime) else datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        if s.tzinfo is None:
            s = s.replace(tzinfo=timezone.utc)
        if ended_at and str(ended_at) not in ("進行中", "已結束"):
            e = ended_at if isinstance(ended_at, datetime) else datetime.fromisoformat(str(ended_at).replace("Z", "+00:00"))
            if e.tzinfo is None:
                e = e.replace(tzinfo=timezone.utc)
        else:
            e = datetime.now(timezone.utc)
        secs = max(0, int((e - s).total_seconds()))
        h, rem = divmod(secs, 3600)
        m, sec = divmod(rem, 60)
        if h > 0:
            return f"{h} 小時 {m} 分 {sec} 秒"
        return f"{m} 分 {sec} 秒"
    except Exception:
        return "—"


_EVENT_LABELS = {
    "SLEEPING": "趴睡 (SLEEPING)",
    "PHONE_SUSPECTED": "疑似滑手機 (PHONE_SUSPECTED)",
    "DISTRACTED": "東張西望/分心 (DISTRACTED)",
    "HEAD_SUPPORT": "托腮撐頭 (HEAD_SUPPORT)",
    "HAND_RAISED": "舉手互動 (HAND_RAISED)",
}


def _build_recommendations(avg_score: float, event_counts: Dict[str, int], max_students: int) -> List[str]:
    recs: List[str] = []
    sleeping_cnt = event_counts.get("SLEEPING", 0)
    phone_cnt = event_counts.get("PHONE_SUSPECTED", 0)
    distracted_cnt = event_counts.get("DISTRACTED", 0) + event_counts.get("HEAD_SUPPORT", 0)
    hand_cnt = event_counts.get("HAND_RAISED", 0)

    if avg_score >= 85.0:
        recs.append("1. 本堂課整體專注度表現優異 (>=85%)，學生多能維持良好聽講姿態，建議維持現行教學節奏。")
    elif avg_score >= 70.0:
        recs.append("1. 本堂課整體專注度屬中等穩定 (70%~84%)，建議於課程中段穿插提問或小組討論以拉升注意力。")
    else:
        recs.append("1. 本堂課平均專注度偏低 (<70%)，建議檢視授課段落長度、加強雙向互動或確認教室空調與照明。")

    if sleeping_cnt > 0 or phone_cnt > 0:
        recs.append(
            f"2. 系統記錄到趴睡 {sleeping_cnt} 次、疑似使用手機 {phone_cnt} 次，建議教師巡堂關懷該座位區學生或適時安排短暫休息。"
        )
    elif distracted_cnt > 0:
        recs.append(
            f"2. 系統偵測到分心或托腮撐頭共 {distracted_cnt} 次，顯示部分時段學生略顯疲勞，可透過實例演示或視覺化教材吸引目光。"
        )
    else:
        recs.append("2. 本堂課未發生趴睡或滑手機等顯著異常行為，課堂秩序相當良好。")

    if hand_cnt > 0:
        recs.append(f"3. 課堂中共有 {hand_cnt} 次舉手互動紀錄，師生雙向參與踴躍，有助於提升學習成效。")
    elif max_students > 0:
        recs.append("3. 本堂課較少偵測到舉手提問，建議下堂課可增設開放式問答或加分搶答環節。")
    else:
        recs.append("3. 尚未在 ROI 座位區內偵測到有效學生人數，請確認攝影機角度與座位區 ROI 設定是否涵蓋學生。")

    return recs


# Simple Client IP Rate Limiter with automatic memory sweep
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

        # Periodic sweep if map grows large to prevent memory leak
        if len(self.requests) > 300:
            stale_ips = [ip for ip, reqs in self.requests.items() if not reqs or (now - reqs[-1] >= self.window_seconds)]
            for ip in stale_ips:
                self.requests.pop(ip, None)


rate_limiter = SimpleRateLimiter(config.API_RATE_LIMIT)


def _render_text_report(
    session_id: str,
    summary: dict,
    started_str: str,
    ended_str: str,
    metrics: Optional[List[dict]] = None,
    events: Optional[List[dict]] = None,
) -> bytes:
    metrics = metrics or []
    events = events or []
    event_counts: Dict[str, int] = defaultdict(int)
    for ev in events:
        code = ev.get("event_code") or database.extract_event_code(str(ev.get("event_type", "")))
        event_counts[code] += 1

    started_fmt = _format_taipei_dt(summary.get("started_at") or started_str)
    ended_fmt = _format_taipei_dt(summary.get("ended_at") or ended_str)
    dur_fmt = _format_duration_str(summary.get("started_at") or started_str, summary.get("ended_at") or ended_str)
    recs = _build_recommendations(
        float(summary.get("avg_attention_score", 100.0)),
        event_counts,
        int(summary.get("max_student_count", 0)),
    )

    event_lines = []
    if event_counts:
        for etype, cnt in event_counts.items():
            label = _EVENT_LABELS.get(etype, etype)
            event_lines.append(f"  - {label}: {cnt} 次")
    else:
        event_lines.append("  - 無異常或特殊事件紀錄")

    report_content = f"""學生專注度與異常行為分析系統 - 課後評估報告
==================================================
課程識別碼: {session_id}
課程名稱: {summary.get('class_name')}
授課教師: {summary.get('teacher')}
教室編號: {summary.get('room') or '未指定'}
開始時間: {started_fmt} (Asia/Taipei)
結束時間: {ended_fmt} (Asia/Taipei)
課程總時長: {dur_fmt}
--------------------------------------------------
統計數據摘要:
最大在線人數: {summary.get('max_student_count', 0)} 人
班級平均專注度: {summary.get('avg_attention_score', 100.0)}%
最低 / 最高專注度: {summary.get('min_attention_score', summary.get('avg_attention_score', 100.0))}% / {summary.get('max_attention_score', summary.get('avg_attention_score', 100.0))}%
累積異常事件次數: {summary.get('total_abnormal_events', 0)} 次
時序採樣點總數: {len(metrics)} 筆
--------------------------------------------------
行為與互動事件統計:
{chr(10).join(event_lines)}
--------------------------------------------------
系統自動教學與環境建議:
{chr(10).join('  ' + r for r in recs)}
==================================================
報告生成時間: {_format_taipei_dt(datetime.now(timezone.utc))} (Asia/Taipei)
"""
    return report_content.encode("utf-8")


def _render_pdf_report(
    session_id: str,
    summary: dict,
    started_str: str,
    ended_str: str,
    metrics: Optional[List[dict]] = None,
    events: Optional[List[dict]] = None,
) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    if metrics is None:
        try:
            metrics = database.get_session_metrics(session_id, limit=1000)
        except Exception:
            metrics = []
    if events is None:
        try:
            events = database.get_session_events(session_id)
        except Exception:
            events = []

    font_name = _get_pdf_font_name()
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=letter)
    c.setTitle(f"學生專注度與異常行為分析課後報告 - {session_id[:8]}")

    started_fmt = _format_taipei_dt(summary.get("started_at") or started_str)
    ended_fmt = _format_taipei_dt(summary.get("ended_at") or ended_str)
    dur_fmt = _format_duration_str(summary.get("started_at") or started_str, summary.get("ended_at") or ended_str)

    # ── 1. Header Banner ──────────────────────────────────────────────────────
    c.setFillColorRGB(0.08, 0.13, 0.24)
    c.rect(0, 725, 612, 70, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont(font_name, 17)
    c.drawString(45, 762, "學生專注度與異常行為分析系統 — 課後評估報告")
    c.setFont(font_name, 9)
    c.setFillColorRGB(0.75, 0.85, 0.98)
    c.drawString(45, 740, f"課程識別碼 (Session UUID): {session_id}    |    Student Analytics & Attention Report")

    # ── 2. Course Metadata ────────────────────────────────────────────────────
    c.setFillColorRGB(0.12, 0.15, 0.2)
    c.setFont(font_name, 11)
    class_name = summary.get("class_name") or "未命名課程"
    teacher = summary.get("teacher") or "未指定"
    room = summary.get("room") or "未指定"
    c.drawString(45, 700, f"課程名稱: {class_name}")
    c.drawString(260, 700, f"授課教師: {teacher}")
    c.drawString(430, 700, f"教室編號: {room}")

    c.setFont(font_name, 10)
    c.setFillColorRGB(0.3, 0.35, 0.42)
    c.drawString(45, 680, f"開始時間: {started_fmt}")
    c.drawString(260, 680, f"結束時間: {ended_fmt}")
    c.drawString(430, 680, f"課程時長: {dur_fmt}")

    c.setStrokeColorRGB(0.82, 0.85, 0.9)
    c.line(45, 668, 567, 668)

    # ── 3. Executive Summary Cards ────────────────────────────────────────────
    c.setFillColorRGB(0.95, 0.97, 1.0)
    c.setStrokeColorRGB(0.75, 0.83, 0.95)
    c.roundRect(45, 575, 522, 82, 6, fill=1, stroke=1)

    c.setFillColorRGB(0.1, 0.2, 0.38)
    c.setFont(font_name, 11)
    c.drawString(58, 638, "【核心統計指標摘要 Executive Summary】")

    avg_score = float(summary.get("avg_attention_score", 100.0))
    min_score = float(summary.get("min_attention_score", avg_score))
    max_score = float(summary.get("max_attention_score", avg_score))
    max_students = int(summary.get("max_student_count", 0))
    total_abnormal = int(summary.get("total_abnormal_events", 0))

    c.setFont(font_name, 10)
    c.setFillColorRGB(0.15, 0.18, 0.22)
    c.drawString(58, 616, f"• 最大在線學生人數 (Peak Student Count): {max_students} 人")
    c.drawString(310, 616, f"• 全班平均專注度 (Average Attention): {avg_score:.1f}%")
    c.drawString(58, 594, f"• 專注度區間 (Min / Max Score): {min_score:.1f}% ~ {max_score:.1f}%")
    c.drawString(310, 594, f"• 累積異常行為次數 (Abnormal Events): {total_abnormal} 次")

    # ── 4. Vector Attention Timeline Chart ────────────────────────────────────
    c.setFillColorRGB(0.1, 0.2, 0.38)
    c.setFont(font_name, 11)
    c.drawString(45, 550, f"【專注度時序變化趨勢圖 Attention Timeline】 (採樣點數: {len(metrics)} 筆)")

    chart_x, chart_y, chart_w, chart_h = 75, 420, 480, 115
    c.setFillColorRGB(0.98, 0.99, 1.0)
    c.setStrokeColorRGB(0.78, 0.82, 0.88)
    c.rect(chart_x, chart_y, chart_w, chart_h, fill=1, stroke=1)

    # Horizontal gridlines (0%, 50%, 80%, 100%)
    c.setFont(font_name, 8)
    for pct in (0, 50, 80, 100):
        gy = chart_y + (pct / 100.0) * chart_h
        c.setStrokeColorRGB(0.88, 0.9, 0.94)
        c.line(chart_x, gy, chart_x + chart_w, gy)
        c.setFillColorRGB(0.4, 0.45, 0.5)
        c.drawRightString(chart_x - 6, gy - 3, f"{pct}%")

    if len(metrics) >= 2:
        # Downsample up to 60 points for smooth PDF vector polyline
        step = max(1, len(metrics) // 60)
        sampled = metrics[::step]
        if sampled[-1] is not metrics[-1]:
            sampled.append(metrics[-1])

        pts = []
        n_pts = len(sampled)
        for idx, m in enumerate(sampled):
            sc = max(0.0, min(100.0, float(m.get("attention_score", 100.0))))
            px = chart_x + (idx / max(1, n_pts - 1)) * chart_w
            py = chart_y + (sc / 100.0) * chart_h
            pts.append((px, py))

        c.setStrokeColorRGB(0.16, 0.48, 0.88)
        c.setLineWidth(1.8)
        for i in range(len(pts) - 1):
            c.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
        c.setLineWidth(1.0)

        # Time axis labels (start & end)
        t_first = _format_taipei_dt(sampled[0].get("timestamp"))[-8:]
        t_last = _format_taipei_dt(sampled[-1].get("timestamp"))[-8:]
        c.setFillColorRGB(0.35, 0.4, 0.45)
        c.drawString(chart_x, chart_y - 12, f"起點 {t_first}")
        c.drawRightString(chart_x + chart_w, chart_y - 12, f"終點 {t_last}")
    elif len(metrics) == 1:
        sc = max(0.0, min(100.0, float(metrics[0].get("attention_score", 100.0))))
        py = chart_y + (sc / 100.0) * chart_h
        c.setStrokeColorRGB(0.16, 0.48, 0.88)
        c.circle(chart_x + chart_w / 2, py, 3, fill=1)
        c.setFillColorRGB(0.4, 0.45, 0.5)
        c.setFont(font_name, 9)
        c.drawCentredString(chart_x + chart_w / 2, chart_y + chart_h / 2 - 4, f"單筆採樣專注度: {sc:.1f}% (課程時長較短)")
    else:
        c.setFillColorRGB(0.45, 0.5, 0.56)
        c.setFont(font_name, 10)
        c.drawCentredString(chart_x + chart_w / 2, chart_y + chart_h / 2 - 4, "尚無足夠時序採樣點可繪製折線圖")

    # ── 5. Event Breakdown & Recent Events Table ──────────────────────────────
    event_counts: Dict[str, int] = defaultdict(int)
    for ev in events:
        code = ev.get("event_code") or database.extract_event_code(str(ev.get("event_type", "")))
        event_counts[code] += 1

    c.setFillColorRGB(0.1, 0.2, 0.38)
    c.setFont(font_name, 11)
    c.drawString(45, 388, "【異常行為與課堂互動統計明細 Event Breakdown】")

    c.setFont(font_name, 9.5)
    c.setFillColorRGB(0.18, 0.22, 0.28)
    summary_parts = []
    for k, label in _EVENT_LABELS.items():
        summary_parts.append(f"{label.split(' ')[0]}: {event_counts.get(k, 0)} 次")
    c.drawString(45, 370, "分類統計:  " + "   |   ".join(summary_parts))

    # Recent events table (up to 8 entries)
    table_top = 352
    c.setFillColorRGB(0.92, 0.95, 0.98)
    c.rect(45, table_top - 16, 522, 16, fill=1, stroke=0)
    c.setFillColorRGB(0.15, 0.2, 0.3)
    c.setFont(font_name, 9)
    c.drawString(52, table_top - 12, "發生時間 (Asia/Taipei)")
    c.drawString(200, table_top - 12, "學生追蹤編號")
    c.drawString(305, table_top - 12, "行為事件類型")
    c.drawString(485, table_top - 12, "持續秒數")

    y_row = table_top - 30
    if events:
        for ev in events[:8]:
            ts_str = _format_taipei_dt(ev.get("timestamp") or ev.get("started_at"))
            tk_id = str(ev.get("tracking_id") or ev.get("student_id") or "S000")
            et_code = ev.get("event_code") or database.extract_event_code(str(ev.get("event_type", "")))
            et_label = _EVENT_LABELS.get(et_code, str(ev.get("event_type", et_code)))
            dur_s = float(ev.get("duration_seconds") or 0.0)
            c.setFillColorRGB(0.2, 0.24, 0.3)
            c.drawString(52, y_row, ts_str)
            c.drawString(200, y_row, tk_id)
            c.drawString(305, y_row, et_label)
            c.drawString(485, y_row, f"{dur_s:.1f} 秒")
            c.setStrokeColorRGB(0.9, 0.92, 0.95)
            c.line(45, y_row - 4, 567, y_row - 4)
            y_row -= 15
    else:
        c.setFillColorRGB(0.4, 0.45, 0.5)
        c.drawString(52, y_row, "本堂課無觸發任何異常行為或舉手事件紀錄。")
        y_row -= 18

    # ── 6. Automated Teaching & Environment Recommendations ───────────────────
    rec_top = min(y_row - 10, 175)
    c.setFillColorRGB(0.96, 0.98, 0.96)
    c.setStrokeColorRGB(0.75, 0.88, 0.78)
    c.roundRect(45, 72, 522, rec_top - 64, 6, fill=1, stroke=1)

    c.setFillColorRGB(0.1, 0.35, 0.18)
    c.setFont(font_name, 10.5)
    c.drawString(55, rec_top - 18, "【AI 課後教學與環境改善建議 Automated Recommendations】")

    recs = _build_recommendations(avg_score, event_counts, max_students)
    c.setFont(font_name, 9)
    c.setFillColorRGB(0.18, 0.24, 0.2)
    ry = rec_top - 36
    for r_line in recs:
        if ry < 80:
            break
        c.drawString(58, ry, r_line)
        ry -= 16

    # ── 7. Footer ─────────────────────────────────────────────────────────────
    c.setFillColorRGB(0.45, 0.5, 0.56)
    c.setFont(font_name, 8.5)
    now_tpe = _format_taipei_dt(datetime.now(timezone.utc))
    c.drawString(45, 42, f"本報告由 學生專注度與異常行為分析系統 (Edge AI YOLOv8-Pose Engine) 自動生成 | 生成時間: {now_tpe} (Asia/Taipei)")

    c.showPage()
    c.save()
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


async def pregenerate_session_report(session_id: str):
    """Background task to pre-generate and cache PDF report when a session ends."""
    summary = await asyncio.to_thread(database.get_session_summary, session_id)
    if not summary:
        return
    metrics = await asyncio.to_thread(database.get_session_metrics, session_id, 1000)
    events = await asyncio.to_thread(database.get_session_events, session_id)
    started_str = summary["started_at"].isoformat() if hasattr(summary["started_at"], "isoformat") else str(summary["started_at"])
    ended_str = summary["ended_at"].isoformat() if summary.get("ended_at") and hasattr(summary["ended_at"], "isoformat") else str(summary.get("ended_at", "已結束"))

    try:
        pdf_bytes = _render_pdf_report(session_id, summary, started_str, ended_str, metrics=metrics, events=events)
        cache_path = os.path.join(REPORTS_CACHE_DIR, f"report_v2_{session_id}.pdf")
        with open(cache_path, "wb") as f:
            f.write(pdf_bytes)
        logger.info(f"Report pre-generated and cached at: {cache_path}")
    except Exception as e:
        logger.warning(f"Report pre-generation failed: {e}")


async def build_session_report_response(session_id: str, request: Request, format_type: str = "pdf"):
    """
    Unified report builder serving both /api/v1/sessions/{id}/report and /api/v1/report/{id}.
    Enforces Rate Limiting, serves pre-cached files if available, and gracefully falls back to text.
    """
    # 1. Enforce Rate Limiting
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_limiter.check_rate_limit(client_ip)

    # 2. Check session existence
    session = await asyncio.to_thread(database.get_session_by_id, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該課程記錄")

    summary = await asyncio.to_thread(database.get_session_summary, session_id)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該課程統計摘要")

    started_str = summary["started_at"].isoformat() if hasattr(summary["started_at"], "isoformat") else str(summary["started_at"])
    ended_str = summary["ended_at"].isoformat() if summary.get("ended_at") and hasattr(summary["ended_at"], "isoformat") else str(summary.get("ended_at", "進行中"))

    # 3. Check for cached PDF if format is PDF (only for ended sessions)
    cache_path = os.path.join(REPORTS_CACHE_DIR, f"report_v2_{session_id}.pdf")
    if format_type == "pdf" and summary.get("ended_at") and os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                cached_bytes = f.read()
            headers = {'Content-Disposition': f'attachment; filename="report_{session_id[:8]}.pdf"'}
            return StreamingResponse(io.BytesIO(cached_bytes), media_type="application/pdf", headers=headers)
        except Exception:
            pass

    metrics = await asyncio.to_thread(database.get_session_metrics, session_id, 1000)
    events = await asyncio.to_thread(database.get_session_events, session_id)

    # 4. Generate on the fly
    if format_type == "pdf":
        try:
            pdf_bytes = _render_pdf_report(
                session_id, summary, started_str, ended_str, metrics=metrics, events=events
            )
            if summary.get("ended_at"):
                try:
                    with open(cache_path, "wb") as f:
                        f.write(pdf_bytes)
                except Exception:
                    pass
            headers = {'Content-Disposition': f'attachment; filename="report_{session_id[:8]}.pdf"'}
            return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)
        except Exception as e:
            logger.warning(f"PDF generation fallback to text triggered (reason: {e})")

    # 5. Text fallback or explicit text request
    text_bytes = _render_text_report(
        session_id, summary, started_str, ended_str, metrics=metrics, events=events
    )
    headers = {'Content-Disposition': f'attachment; filename="report_{session_id[:8]}.txt"'}
    return StreamingResponse(io.BytesIO(text_bytes), media_type="text/plain; charset=utf-8", headers=headers)


@router.get(
    "/report/{session_id}",
    summary="產生並下載課程 PDF / 摘要報告 (舊版相容端點)",
    description=f"依據課程 UUID 生成課後 PDF/文本 統計報告。受 API 速率限制 ({config.API_RATE_LIMIT}) 保護。"
)
async def generate_and_download_report(
    session_id: str,
    request: Request,
    format: str = Query("pdf", pattern="^(pdf|txt)$", description="報告格式: pdf 或 txt")
):
    return await build_session_report_response(session_id, request, format_type=format)
