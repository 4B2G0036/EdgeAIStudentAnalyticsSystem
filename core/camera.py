import cv2
import time
import logging
import config

logger = logging.getLogger("core.camera")

class CameraConnectionError(Exception):
    """Exception raised when camera connection fails after max retries."""
    pass

class CameraManager:
    def __init__(self, camera_id=None):
        self.camera_id = camera_id if camera_id is not None else config.CAMERA_ID
        self.cap = None
        self.last_inference_time = 0.0
        self.throttle_interval = 1.0 / config.TARGET_FPS  # 0.2 seconds for 5 FPS

    def connect(self):
        """Connect to the camera with retry logic (1s interval, max 10 retries)."""
        retries = 10
        for i in range(retries):
            logger.info(f"Connecting to camera {self.camera_id} (Attempt {i+1}/{retries})...")
            cid = self.camera_id
            if isinstance(cid, str) and cid.isdigit():
                cid = int(cid)
            
            try:
                self.cap = cv2.VideoCapture(cid)
                if self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if ret:
                        logger.info(f"Successfully connected to camera {self.camera_id}")
                        self.last_inference_time = time.time()
                        return
                    else:
                        logger.warning("Camera opened but failed to read initial frame.")
            except Exception as e:
                logger.error(f"Error during video capture open: {e}")
                
            self.disconnect()
            time.sleep(1.0)
            
        logger.error(f"Failed to connect to camera {self.camera_id} after {retries} attempts.")
        raise CameraConnectionError(f"Could not connect to camera {self.camera_id}")

    def read_frame(self) -> tuple[bool, cv2.Mat]:
        """
        Read the next frame from camera.
        Enforces 5 FPS throttle by active reading and discarding extra frames from buffer.
        """
        if self.cap is None or not self.cap.isOpened():
            logger.warning("Camera not open, attempting to reconnect...")
            self.connect()

        now = time.time()
        time_since_last = now - self.last_inference_time
        
        # If we are polling too fast, keep grabbing frames from the hardware buffer and discard them
        if time_since_last < self.throttle_interval:
            # Drop frames to empty OpenCV buffer and avoid lag
            while time.time() - self.last_inference_time < self.throttle_interval:
                # grab() retrieves the next frame but does not decompress it (fast discard)
                self.cap.grab()
                time.sleep(0.001)  # small pause to yield CPU

        # Decode and retrieve the frame
        ret, frame = self.cap.read()
        if not ret:
            logger.warning("Failed to read frame from camera.")
            return False, None
            
        self.last_inference_time = time.time()
        return True, frame

    def disconnect(self):
        """Release camera resource."""
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception as e:
                logger.error(f"Error releasing camera: {e}")
            self.cap = None
            logger.info("Camera disconnected.")
