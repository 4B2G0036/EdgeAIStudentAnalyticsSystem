import cv2
import time
import logging
import config

logger = logging.getLogger("core.camera")

class CameraConnectionError(Exception):
    """Exception raised when camera connection fails."""
    pass

class CameraManager:
    def __init__(self, camera_id=None):
        self.camera_id = camera_id if camera_id is not None else config.CAMERA_ID
        self.cap = None
        self.last_inference_time = 0.0
        self.last_connect_attempt = 0.0
        self.connect_cooldown = 5.0  # Cooldown between reconnection attempts if failed
        self.throttle_interval = 1.0 / config.TARGET_FPS  # 0.2 seconds for 5 FPS

    def connect(self) -> bool:
        """Attempt to connect to the camera without long blocking delays."""
        now = time.time()
        if now - self.last_connect_attempt < self.connect_cooldown:
            return False

        self.last_connect_attempt = now
        cid = self.camera_id
        if isinstance(cid, str) and cid.isdigit():
            cid = int(cid)

        logger.info(f"Connecting to camera {self.camera_id}...")
        try:
            # On Windows, try DirectShow (cv2.CAP_DSHOW) if numerical ID, or default
            if isinstance(cid, int):
                cap = cv2.VideoCapture(cid, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(cid)
            else:
                cap = cv2.VideoCapture(cid)

            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    self.cap = cap
                    logger.info(f"Successfully connected to camera {self.camera_id}")
                    self.last_inference_time = time.time()
                    return True
                else:
                    logger.warning("Camera opened but failed to read initial frame.")
                    cap.release()
        except Exception as e:
            logger.error(f"Error during video capture open: {e}")

        self.disconnect()
        return False

    def read_frame(self) -> tuple[bool, cv2.Mat]:
        """
        Read the next frame from camera.
        Enforces 5 FPS throttle. Returns (False, None) if camera unavailable.
        """
        if self.cap is None or not self.cap.isOpened():
            connected = self.connect()
            if not connected:
                return False, None

        now = time.time()
        time_since_last = now - self.last_inference_time
        
        if time_since_last < self.throttle_interval:
            time.sleep(max(0.001, self.throttle_interval - time_since_last))

        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                logger.warning("Failed to read frame from camera, releasing...")
                self.disconnect()
                return False, None

            self.last_inference_time = time.time()
            return True, frame
        except Exception as e:
            logger.error(f"Exception reading camera frame: {e}")
            self.disconnect()
            return False, None

    def disconnect(self):
        """Release camera resource."""
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception as e:
                logger.error(f"Error releasing camera: {e}")
            self.cap = None
            logger.info("Camera disconnected.")
