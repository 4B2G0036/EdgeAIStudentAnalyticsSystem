import cv2
import time
import random
import asyncio
import queue
import threading
import logging
from datetime import datetime
from typing import Optional, Set
from fastapi import APIRouter, Response, HTTPException, status
from fastapi.responses import StreamingResponse

import config
import database
from core.camera import CameraManager
from core.pose_analyzer import PoseAnalyzer
from core.drawing import draw_text_bgr
from api.persistence import get_persister
from api.routers.realtime import update_live_state

logger = logging.getLogger("api.routers.stream")
router = APIRouter(prefix="/api/v1", tags=["攝影機實時串流與監控"])

# Global CameraManager and StreamBroadcaster instances
_camera_manager = None
_broadcaster: Optional["StreamBroadcaster"] = None

def get_camera_manager():
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager(config.CAMERA_ID)
    return _camera_manager

_FALLBACK_BG = None


def _get_fallback_background():
    """Build the dark gradient background once (vectorized) and reuse a copy per frame."""
    global _FALLBACK_BG
    if _FALLBACK_BG is None:
        import numpy as np
        y = np.arange(480, dtype=np.float32)[:, None]
        base = np.array([10, 14, 26], dtype=np.float32)
        step = np.array([0.03, 0.04, 0.05], dtype=np.float32)
        gradient = (base + y * step).astype(np.uint8)            # (480, 3)
        _FALLBACK_BG = np.repeat(gradient[:, None, :], 640, axis=1)  # (480, 640, 3)
    return _FALLBACK_BG.copy()


def generate_fallback_frame(text="攝影機串流傳輸中 (等待畫面)..."):
    """Generate a clean dark-themed placeholder frame if hardware camera fails to open."""
    img = _get_fallback_background()
        # Draw header banner
    cv2.rectangle(img, (0, 0), (640, 45), (15, 22, 41), -1)
    draw_text_bgr(img, "STUDENT ANALYTICS AI STREAM (LIVE 5 FPS)", (15, 12), font_size=15, color_bgr=(99, 179, 237), bold=True)
                
    # Draw time string
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    draw_text_bgr(img, f"TIME: {time_str}", (420, 14), font_size=13, color_bgr=(136, 146, 176), bold=False)
                
    # Draw center box
    cv2.rectangle(img, (80, 100), (560, 380), (30, 40, 65), 2)
    draw_text_bgr(img, "AI VISION CORE STREAM", (200, 215), font_size=20, color_bgr=(232, 234, 246), bold=True)
    draw_text_bgr(img, text, (180, 260), font_size=15, color_bgr=(79, 209, 199), bold=True)
                
    # Draw animated live indicator
    second = int(time.time())
    if second % 2 == 0:
        cv2.circle(img, (530, 22), 6, (104, 211, 145), -1)
        draw_text_bgr(img, "LIVE", (545, 14), font_size=13, color_bgr=(104, 211, 145), bold=True)
    else:
        cv2.circle(img, (530, 22), 6, (74, 85, 104), -1)
        draw_text_bgr(img, "LIVE", (545, 14), font_size=13, color_bgr=(136, 146, 176), bold=True)

    # Encode to JPEG
    ret, jpeg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return jpeg.tobytes()


class StreamBroadcaster:
    """
    Thread-safe Single Producer - Multiple Consumers Frame Broadcaster.
    
    Guarantees:
      1. Only 1 thread accesses OpenCV CameraManager.
      2. AI Inference (YOLOv8-Pose) executes at most once per frame interval, regardless of listener count.
      3. Zero CPU when 0 clients are subscribed (worker idles on threading.Event).
      4. Drop-frame protection so slow/jittery network clients never build up latency.
    """
    def __init__(self):
        self._subscribers: Set[queue.Queue] = set()
        self._lock = threading.Lock()
        self._has_subscribers = threading.Event()
        self._stop_event = threading.Event()
        self._latest_frame: Optional[bytes] = None
        self._worker_thread: Optional[threading.Thread] = None

    @property
    def viewer_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def start(self):
        with self._lock:
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._stop_event.clear()
                self._worker_thread = threading.Thread(
                    target=self._run_loop,
                    name="StreamBroadcasterWorker",
                    daemon=True
                )
                self._worker_thread.start()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=2)
        with self._lock:
            if self._latest_frame is not None:
                try:
                    q.put_nowait(self._latest_frame)
                except queue.Full:
                    pass
            self._subscribers.add(q)
            self._has_subscribers.set()
            count = len(self._subscribers)
        self.start()
        logger.info(f"Stream client connected. Active subscribers: {count}")
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            self._subscribers.discard(q)
            count = len(self._subscribers)
            if count == 0:
                self._has_subscribers.clear()
        logger.info(f"Stream client disconnected. Active subscribers: {count}")

    def _broadcast_frame(self, frame_bytes: bytes):
        self._latest_frame = frame_bytes
        with self._lock:
            for q in list(self._subscribers):
                try:
                    if q.full():
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            pass
                    q.put_nowait(frame_bytes)
                except Exception:
                    pass

    def _run_loop(self):
        logger.info("StreamBroadcaster background worker started.")
        cam = get_camera_manager()
        analyzer = PoseAnalyzer.get_instance()
        throttle = 1.0 / config.TARGET_FPS

        while not self._stop_event.is_set():
            # Idle and conserve CPU when no subscribers are watching
            if not self._has_subscribers.wait(timeout=0.5):
                continue

            start_time = time.time()
            frame_bytes = None

            try:
                success, frame = cam.read_frame()
                if success and frame is not None:
                    # Run YOLOv8-Pose AI inference with bounding box & skeleton overlay
                    analysis = analyzer.analyze_frame(frame, draw_overlay=True)
                    annotated_frame = analysis["annotated_frame"]

                    score = analysis["attention_score"]
                    count = analysis["student_count"]
                    latest_event = analysis["latest_event"]
                    events = analysis["events"]

                    # Update live in-memory state
                    update_live_state(score, count, latest_event, events)

                    # Persist to DB if session is active (session cached, events lifecycle-aware)
                    get_persister().persist(score, count, events)

                    # Add overlay banner with timestamp and stats
                    height, width = annotated_frame.shape[:2]
                    cv2.rectangle(annotated_frame, (0, 0), (width, 35), (10, 14, 26), -1)
                    time_str = datetime.now().strftime("%H:%M:%S")
                    stats_str = f"人數: {count} | 專注度: {score:.0f}分 | {time_str}"
                    draw_text_bgr(
                        annotated_frame,
                        f"[AI CORE LIVE] {stats_str}",
                        (15, 8),
                        font_size=14,
                        color_bgr=(79, 209, 199),
                        bold=True,
                    )

                    ret, jpeg = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    if ret:
                        frame_bytes = jpeg.tobytes()
            except Exception as e:
                logger.warning(f"Error in stream processing: {e}")

            if frame_bytes is None:
                frame_bytes = generate_fallback_frame("攝影機等待畫面中...")

            self._broadcast_frame(frame_bytes)

            elapsed = time.time() - start_time
            sleep_dur = max(0.01, throttle - elapsed)
            time.sleep(sleep_dur)

        logger.info("StreamBroadcaster background worker stopped.")


def get_stream_broadcaster() -> StreamBroadcaster:
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = StreamBroadcaster()
    return _broadcaster


def mjpeg_frame_generator():
    """Generator yielding broadcasted camera frames to a connected client."""
    broadcaster = get_stream_broadcaster()
    q = broadcaster.subscribe()
    try:
        while True:
            try:
                frame_bytes = q.get(timeout=2.0)
            except queue.Empty:
                frame_bytes = broadcaster._latest_frame or generate_fallback_frame("攝影機等待畫面中...")
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    finally:
        broadcaster.unsubscribe(q)


@router.get(
    "/stream",
    summary="實時 MJPEG 攝影機影像串流 (含 AI 骨架分析標註)",
    description="提供符合 RFC 1341 標準之 multipart/x-mixed-replace MJPEG 攝影機影像串流，內建 YOLOv8-Pose 骨架標註與即時姿態警報。"
)
async def get_live_camera_stream():
    return StreamingResponse(
        mjpeg_frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@router.get(
    "/camera/status",
    summary="查詢攝影機連線狀態",
    description="取得目前邊緣端攝影機之硬體識別碼、FPS 鎖定與運作狀態。"
)
async def get_camera_status():
    cam = get_camera_manager()
    is_open = cam.cap is not None and cam.cap.isOpened()
    broadcaster = get_stream_broadcaster()
    return {
        "camera_id": config.CAMERA_ID,
        "is_connected": is_open,
        "target_fps": config.TARGET_FPS,
        "resolution": "640x480",
        "status": "online" if is_open else "standby",
        "active_viewers": broadcaster.viewer_count
    }
