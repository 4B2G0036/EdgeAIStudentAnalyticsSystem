"""
core/camera.py
==============
Hardware Camera Manager with 5 FPS hardware buffer flushing and automatic retry.

Key Specifications
------------------
- Maximum FPS: 5 FPS (200 ms throttle interval per frame).
- Active Buffer Flushing: Discards intermediate frames via cap.read() rather than
  using time.sleep(), preventing stale buffered frames from accumulating.
- Reconnection Policy: Retries up to 10 times at 1.0 s intervals upon connection loss
  before raising CameraConnectionError.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

import cv2
import numpy as np

import config

logger = logging.getLogger("core.camera")


class CameraConnectionError(Exception):
    """Exception raised when camera hardware cannot be accessed or disconnected."""
    pass


class CameraManager:
    """
    Manages connection, active frame reading, and buffer flushing for video capture.
    """

    def __init__(
        self,
        camera_id: Optional[int | str] = None,
        target_fps: Optional[float] = None,
        max_reconnect_retries: int = 10,
        retry_interval_s: float = 1.0,
    ) -> None:
        self.camera_id = camera_id if camera_id is not None else getattr(config, "CAMERA_ID", 0)
        fps = target_fps if target_fps is not None else getattr(config, "TARGET_FPS", 5.0)
        self.throttle_interval = 1.0 / max(0.1, float(fps))
        self.max_retries = max_reconnect_retries
        self.retry_interval = retry_interval_s

        self.cap: Optional[cv2.VideoCapture] = None
        self.last_frame_time: float = 0.0
        self._is_connected: bool = False

    def connect(self, raise_on_failure: bool = False) -> bool:
        """
        Attempt to establish connection to the camera.
        Retries up to `max_retries` with `retry_interval` delay.

        Parameters
        ----------
        raise_on_failure : If True, raises CameraConnectionError if unable to connect.
        """
        cid = self.camera_id
        if isinstance(cid, str) and cid.isdigit():
            cid = int(cid)

        logger.info("Attempting connection to camera '%s'...", self.camera_id)

        for attempt in range(1, self.max_retries + 1):
            try:
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None

                # On Windows, DirectShow (cv2.CAP_DSHOW) provides faster startup for USB webcams
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
                        self._is_connected = True
                        self.last_frame_time = time.time()
                        logger.info(
                            "Camera '%s' successfully connected on attempt %d/%d.",
                            self.camera_id, attempt, self.max_retries
                        )
                        return True
                    else:
                        cap.release()

            except Exception as exc:
                logger.warning(
                    "Camera connection attempt %d/%d failed: %s",
                    attempt, self.max_retries, exc
                )

            if attempt < self.max_retries:
                time.sleep(self.retry_interval)

        self._is_connected = False
        msg = f"Failed to connect to camera '{self.camera_id}' after {self.max_retries} attempts."
        logger.error(msg)
        if raise_on_failure:
            raise CameraConnectionError(msg)
        return False

    def read_frame(self, raise_on_error: bool = False) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read the freshest frame, actively discarding queued buffer frames until
        the throttle interval (e.g. 200ms for 5 FPS) has elapsed.

        Strictly avoids time.sleep() during active capture to prevent stale hardware buffers.

        Returns
        -------
        (success, frame) : (True, ndarray) if frame retrieved, (False, None) otherwise.
        """
        if self.cap is None or not self.cap.isOpened():
            connected = self.connect(raise_on_failure=raise_on_error)
            if not connected:
                return False, None

        # Active frame retrieval and buffer flushing loop
        while True:
            try:
                ret, frame = self.cap.read()
            except Exception as e:
                logger.error("Exception in cap.read(): %s", e)
                ret, frame = False, None

            if not ret or frame is None:
                logger.warning("Camera stream read failed. Attempting reconnection...")
                self.disconnect()
                reconnected = self.connect(raise_on_failure=raise_on_error)
                if not reconnected:
                    return False, None
                continue

            now = time.time()
            elapsed = now - self.last_frame_time

            # If enough time has passed for target FPS (>= 200 ms for 5 FPS), emit this frame!
            if elapsed >= self.throttle_interval:
                self.last_frame_time = now
                return True, frame

            # Otherwise, frame was read and discarded to keep buffer fresh.
            # Small 1ms yield prevents tight 100% core spin on mock/virtual cameras.
            time.sleep(0.001)

    def disconnect(self) -> None:
        """Safely release the camera resource."""
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception as exc:
                logger.error("Error releasing camera resource: %s", exc)
            self.cap = None
        self._is_connected = False
        logger.info("Camera '%s' disconnected.", self.camera_id)

    def __enter__(self) -> "CameraManager":
        self.connect(raise_on_failure=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
