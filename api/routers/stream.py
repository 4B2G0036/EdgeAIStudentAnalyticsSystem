import cv2
import time
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Response, HTTPException, status
from fastapi.responses import StreamingResponse

import config
from core.camera import CameraManager

logger = logging.getLogger("api.routers.stream")
router = APIRouter(prefix="/api/v1", tags=["攝影機實時串流與監控"])

# Global CameraManager instance
_camera_manager = None

def get_camera_manager():
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager(config.CAMERA_ID)
    return _camera_manager

def generate_fallback_frame(text="攝影機串流傳輸中..."):
    """Generate a clean dark-themed placeholder frame if hardware camera fails to open."""
    import numpy as np
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Dark gradient background
    for y in range(480):
        img[y, :] = (int(10 + y * 0.03), int(14 + y * 0.04), int(26 + y * 0.05))
        
    # Draw header banner
    cv2.rectangle(img, (0, 0), (640, 45), (15, 22, 41), -1)
    cv2.putText(img, "STUDENT ANALYTICS AI STREAM (LIVE 5 FPS)", (15, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (99, 179, 237), 2, cv2.LINE_AA)
                
    # Draw time string
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(img, f"TIME: {time_str}", (420, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (136, 146, 176), 1, cv2.LINE_AA)
                
    # Draw center box
    cv2.rectangle(img, (80, 100), (560, 380), (30, 40, 65), 2)
    cv2.putText(img, "AI VISION CORE STREAM", (200, 220), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (232, 234, 246), 2, cv2.LINE_AA)
    cv2.putText(img, text, (210, 260), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (79, 209, 199), 1, cv2.LINE_AA)
                
    # Draw animated live indicator
    second = int(time.time())
    if second % 2 == 0:
        cv2.circle(img, (530, 28), 6, (104, 211, 145), -1)
        cv2.putText(img, "LIVE", (545, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (104, 211, 145), 1, cv2.LINE_AA)
    else:
        cv2.circle(img, (530, 28), 6, (74, 85, 104), -1)
        cv2.putText(img, "LIVE", (545, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (136, 146, 176), 1, cv2.LINE_AA)

    # Encode to JPEG
    ret, jpeg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return jpeg.tobytes()

def mjpeg_frame_generator():
    """Generator for streaming camera frames formatted for MJPEG Boundary response."""
    cam = get_camera_manager()
    throttle = 1.0 / config.TARGET_FPS
    
    while True:
        start_time = time.time()
        frame_bytes = None
        
        try:
            success, frame = cam.read_frame()
            if success and frame is not None:
                # Add overlay banner with timestamp
                height, width = frame.shape[:2]
                cv2.rectangle(frame, (0, 0), (width, 35), (10, 14, 26), -1)
                time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cv2.putText(frame, f"[AI CORE LIVE] {time_str} | 5 FPS", (15, 24), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (79, 209, 199), 1, cv2.LINE_AA)
                
                ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ret:
                    frame_bytes = jpeg.tobytes()
        except Exception as e:
            logger.warning(f"Error reading camera frame: {e}")
            
        if frame_bytes is None:
            # Fallback frame
            frame_bytes = generate_fallback_frame("攝影機即時監控中 (模擬模式)")

        # MJPEG multipart frame formatting
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
               
        # Control FPS loop interval
        elapsed = time.time() - start_time
        sleep_dur = max(0.01, throttle - elapsed)
        time.sleep(sleep_dur)

@router.get(
    "/stream",
    summary="實時 MJPEG 攝影機影像串流",
    description="提供符合 RFC 1341 標準之 multipart/x-mixed-replace MJPEG 攝影機影像串流，供前端控制台 <img> 標籤直接掛載。"
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
    return {
        "camera_id": config.CAMERA_ID,
        "is_connected": is_open,
        "target_fps": config.TARGET_FPS,
        "resolution": "640x480",
        "status": "online" if is_open else "simulated"
    }
