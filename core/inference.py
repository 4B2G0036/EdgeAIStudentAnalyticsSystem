"""
core/inference.py
=================
Pure ONNX Runtime inference engine for YOLOv8-Pose.

Handles:
- Model loading with CUDA → CPU fallback
- Letterbox pre-processing (pad to square, preserve aspect ratio)
- Coordinate de-letterboxing back to original image resolution
- Post-processing: confidence filter + vectorised NMS
- Decoding the [1, 56, 8400] output into (boxes_xyxy, keypoints, scores)

Does NOT depend on ultralytics at runtime – only onnxruntime + numpy + cv2.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Optional

import cv2
import numpy as np
import onnxruntime as ort

import config

logger = logging.getLogger("core.inference")

# ── Constants ──────────────────────────────────────────────────────────────────
NUM_KEYPOINTS = 17       # COCO skeleton
COCO_KPT_STRIDE = 3     # (x, y, conf) per keypoint


def _letterbox(
    img: np.ndarray,
    target_size: int = 640,
    color: tuple[int, int, int] = (114, 114, 114),
) -> tuple[np.ndarray, float, int, int]:
    """
    Resize image to (target_size × target_size) maintaining aspect ratio with
    grey border padding.

    Returns
    -------
    padded_img : (target_size, target_size, 3) uint8 BGR image
    scale      : scalar by which original dimensions were scaled
    pad_left   : horizontal padding applied (pixels on each side)
    pad_top    : vertical padding applied (pixels on each side)
    """
    h, w = img.shape[:2]
    scale = min(target_size / h, target_size / w)
    new_h, new_w = int(round(h * scale)), int(round(w * scale))

    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    pad_h = target_size - new_h
    pad_w = target_size - new_w
    pad_top  = pad_h // 2
    pad_left = pad_w // 2

    padded = cv2.copyMakeBorder(
        resized,
        pad_top, pad_h - pad_top,
        pad_left, pad_w - pad_left,
        cv2.BORDER_CONSTANT, value=color,
    )
    return padded, scale, pad_left, pad_top


def _nms(
    boxes: np.ndarray,   # (N, 4) xyxy
    scores: np.ndarray,  # (N,)
    iou_thresh: float = 0.45,
) -> list[int]:
    """Vectorised greedy NMS.  Returns kept indices sorted by descending score."""
    order = np.argsort(scores)[::-1]
    keep: list[int] = []

    while len(order):
        i = order[0]
        keep.append(int(i))
        if len(order) == 1:
            break
        rest = order[1:]

        # IoU against the best surviving box
        xi1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yi1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xi2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yi2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.maximum(0.0, xi2 - xi1) * np.maximum(0.0, yi2 - yi1)
        area_i    = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        area_rest = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
        union = area_i + area_rest - inter
        ious = inter / (union + 1e-9)

        order = rest[ious < iou_thresh]

    return keep


def _xywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
    """Convert centre-format (cx,cy,w,h) to corner-format (x1,y1,x2,y2)."""
    out = np.empty_like(boxes)
    out[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
    out[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
    out[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
    out[:, 3] = boxes[:, 1] + boxes[:, 3] / 2
    return out


# ── Main Engine ────────────────────────────────────────────────────────────────
class InferenceEngine:
    """
    YOLOv8-Pose ONNX inference engine.

    Usage
    -----
    engine = InferenceEngine()
    engine.load("models/yolov8n-pose.onnx")
    boxes, kpts, scores = engine.infer(frame_bgr)
    """

    _instance: Optional["InferenceEngine"] = None

    def __init__(self) -> None:
        self._session: Optional[ort.InferenceSession] = None
        self._input_name: str = "images"
        self._img_size: int = getattr(config, "IMG_SZ", 640)
        self._conf_thresh: float = getattr(config, "POSE_CONF_THRESHOLD", 0.35)
        self._iou_thresh: float = 0.45
        self._provider: str = "CPUExecutionProvider"

    # ── Class-level singleton ──────────────────────────────────────────────────
    @classmethod
    def get_instance(cls) -> "InferenceEngine":
        if cls._instance is None:
            cls._instance = InferenceEngine()
            cls._instance.load()
        return cls._instance

    # ── Model loading ──────────────────────────────────────────────────────────
    def load(self, model_path: Optional[str] = None) -> None:
        """
        Load the ONNX model.  Tries CUDAExecutionProvider first; falls back to CPU.

        Parameters
        ----------
        model_path : str or None
            Explicit path to .onnx file.  When None the default search order is:
            1. models/yolov8n-pose.onnx  (next to project root)
            2. yolov8n-pose.onnx         (project root)
        """
        if model_path is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            candidates = [
                os.path.join(base, "models", "yolov8n-pose.onnx"),
                os.path.join(base, "yolov8n-pose.onnx"),
            ]
            model_path = next((p for p in candidates if os.path.exists(p)), candidates[0])

        # Provider selection
        available = ort.get_available_providers()
        if "CUDAExecutionProvider" in available:
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            self._provider = "CUDAExecutionProvider"
        else:
            providers = ["CPUExecutionProvider"]
            self._provider = "CPUExecutionProvider"
            logger.warning("CUDAExecutionProvider unavailable – using CPU inference. "
                           "Performance may be insufficient for real-time use.")

        self._session = ort.InferenceSession(model_path, providers=providers)
        self._input_name = self._session.get_inputs()[0].name
        logger.info(
            "InferenceEngine loaded model='%s'  provider=%s  device=%s",
            os.path.basename(model_path),
            self._provider,
            ort.get_device(),
        )

    # ── Core inference ─────────────────────────────────────────────────────────
    def infer(
        self,
        frame_bgr: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
        """
        Run one forward pass on a BGR image and decode the detections.

        Parameters
        ----------
        frame_bgr : np.ndarray  shape (H, W, 3)  uint8 BGR image

        Returns
        -------
        boxes_xyxy : (N, 4) float32   pixel coordinates in original image space
        keypoints  : (N, 17, 3) float32  (x_px, y_px, conf) in original image space
        scores     : (N,) float32         detection confidence
        trace_id   : str                  unique UUID for this frame
        """
        if self._session is None:
            raise RuntimeError("InferenceEngine.load() must be called before infer().")

        trace_id = str(uuid.uuid4())
        orig_h, orig_w = frame_bgr.shape[:2]

        # 1. Pre-process
        padded, scale, pad_left, pad_top = _letterbox(frame_bgr, self._img_size)
        rgb     = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor  = np.transpose(rgb, (2, 0, 1))[np.newaxis, :]   # [1,3,H,W]

        # 2. Forward pass
        t0 = time.perf_counter()
        raw_out = self._session.run(None, {self._input_name: tensor})[0]  # [1,56,8400]
        inference_ms = (time.perf_counter() - t0) * 1000.0
        logger.debug("trace_id=%s  inference_time=%.1fms  provider=%s",
                     trace_id, inference_ms, self._provider)

        # 3. Decode  [1, 56, 8400] → [8400, 56]
        preds = raw_out[0].T  # (8400, 56)

        boxes_xywh = preds[:, :4]        # cx, cy, w, h  (in letterbox space)
        obj_scores = preds[:, 4]         # objectness
        kpts_raw   = preds[:, 5:]        # (8400, 51)  = 17*(x,y,conf)

        # 4. Confidence filter
        mask = obj_scores >= self._conf_thresh
        if not mask.any():
            return (
                np.zeros((0, 4),    dtype=np.float32),
                np.zeros((0, 17, 3), dtype=np.float32),
                np.zeros((0,),      dtype=np.float32),
                trace_id,
            )

        boxes_xywh = boxes_xywh[mask]
        scores     = obj_scores[mask]
        kpts_raw   = kpts_raw[mask]

        # 5. Convert boxes to xyxy in letterbox space then NMS
        boxes_xyxy_lb = _xywh_to_xyxy(boxes_xywh)
        keep = _nms(boxes_xyxy_lb, scores, self._iou_thresh)

        boxes_xyxy_lb = boxes_xyxy_lb[keep]
        scores        = scores[keep]
        kpts_raw      = kpts_raw[keep]

        # 6. De-letterbox: map back to original image pixel coordinates
        def _delb_xy(x_lb, y_lb):
            """Convert single (x, y) point from letterbox space to original."""
            x_orig = (x_lb - pad_left) / scale
            y_orig = (y_lb - pad_top)  / scale
            return (
                float(np.clip(x_orig, 0, orig_w)),
                float(np.clip(y_orig, 0, orig_h)),
            )

        N = len(keep)
        boxes_out = np.zeros((N, 4),     dtype=np.float32)
        kpts_out  = np.zeros((N, 17, 3), dtype=np.float32)

        for i in range(N):
            x1, y1 = _delb_xy(boxes_xyxy_lb[i, 0], boxes_xyxy_lb[i, 1])
            x2, y2 = _delb_xy(boxes_xyxy_lb[i, 2], boxes_xyxy_lb[i, 3])
            boxes_out[i] = [x1, y1, x2, y2]

            for k in range(NUM_KEYPOINTS):
                kx_lb = kpts_raw[i, k * COCO_KPT_STRIDE]
                ky_lb = kpts_raw[i, k * COCO_KPT_STRIDE + 1]
                kc    = float(kpts_raw[i, k * COCO_KPT_STRIDE + 2])
                kx, ky = _delb_xy(kx_lb, ky_lb)
                kpts_out[i, k] = [kx, ky, kc]

        return boxes_out, kpts_out, scores.astype(np.float32), trace_id
