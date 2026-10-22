"""
core/privacy.py
===============
Privacy protection: Gaussian blur on head / face regions.

Rule: ALL blurring MUST happen BEFORE any label or annotation is drawn.
      Raw face pixels must NEVER leave this module visible to downstream callers.

Implementation
--------------
- Uses detected bounding-boxes (or keypoint-derived head patches as fallback)
  to locate each person's head region.
- Applies cv2.GaussianBlur with kernel size ≥ 31 × 31 (from config).
- Returns the privacy-safe annotated copy; the original frame is NOT mutated.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

import config

logger = logging.getLogger("core.privacy")

# COCO keypoint indices (head-related)
_NOSE      = 0
_LEFT_EYE  = 1
_RIGHT_EYE = 2
_LEFT_EAR  = 3
_RIGHT_EAR = 4

_CONF_THRESH = 0.25   # lower threshold to maximise blur coverage


def _get_blur_kernel() -> tuple[int, int]:
    """Return the Gaussian kernel size (always odd, ≥ 31)."""
    k = getattr(config, "PII_BLUR_KERNEL", 31)
    if isinstance(k, (tuple, list)):
        k = max(k)
    k = max(31, int(k))
    if k % 2 == 0:
        k += 1
    return (k, k)


def _head_roi_from_bbox(
    bbox: np.ndarray,
    frame_h: int,
    frame_w: int,
) -> tuple[int, int, int, int]:
    """
    Estimate head ROI as the *top 35 %* of the person bounding-box.

    Parameters
    ----------
    bbox : (4,) float32  xyxy pixel coords

    Returns
    -------
    (x1, y1, x2, y2) int  clamped to frame dimensions
    """
    x1, y1, x2, y2 = [int(v) for v in bbox]
    h = y2 - y1
    head_y2 = y1 + int(h * 0.35)
    return (
        max(0, x1),
        max(0, y1),
        min(frame_w, x2),
        min(frame_h, head_y2),
    )


def _head_roi_from_keypoints(
    kpts: np.ndarray,
    frame_h: int,
    frame_w: int,
    padding: float = 0.15,
) -> tuple[int, int, int, int] | None:
    """
    Derive head ROI from visible face keypoints (nose, eyes, ears).

    Returns None when no face keypoints are visible.
    """
    HEAD_KPT_IDX = [_NOSE, _LEFT_EYE, _RIGHT_EYE, _LEFT_EAR, _RIGHT_EAR]
    valid_pts = [
        kpts[i, :2]
        for i in HEAD_KPT_IDX
        if kpts[i, 2] >= _CONF_THRESH
    ]
    if not valid_pts:
        return None

    pts = np.stack(valid_pts)
    xmin, ymin = pts[:, 0].min(), pts[:, 1].min()
    xmax, ymax = pts[:, 0].max(), pts[:, 1].max()

    # Add generous padding around the face keypoints
    dx = max(20.0, (xmax - xmin) * padding)
    dy = max(20.0, (ymax - ymin) * padding)

    return (
        max(0, int(xmin - dx)),
        max(0, int(ymin - dy)),
        min(frame_w, int(xmax + dx)),
        min(frame_h, int(ymax + dy)),
    )


def apply_privacy_blur(
    frame: np.ndarray,
    boxes_xyxy: np.ndarray,         # (N, 4) float32  xyxy pixel coords
    keypoints:  np.ndarray,         # (N, 17, 3) float32
) -> np.ndarray:
    """
    Apply Gaussian blur to all detected head regions and return the
    privacy-safe copy of the frame.

    IMPORTANT: call this BEFORE drawing any skeleton/label overlays.

    Parameters
    ----------
    frame      : (H, W, 3) uint8 BGR
    boxes_xyxy : (N, 4)
    keypoints  : (N, 17, 3)

    Returns
    -------
    blurred_frame : (H, W, 3) uint8 – original pixels preserved outside head regions
    """
    out     = frame.copy()
    h, w    = frame.shape[:2]
    kernel  = _get_blur_kernel()
    blurred = None  # lazy compute

    for i in range(len(boxes_xyxy)):
        kpts = keypoints[i]

        # Prefer keypoint-derived ROI for precision, fallback to bbox
        roi = _head_roi_from_keypoints(kpts, h, w)
        if roi is None:
            roi = _head_roi_from_bbox(boxes_xyxy[i], h, w)

        rx1, ry1, rx2, ry2 = roi
        if rx2 <= rx1 or ry2 <= ry1:
            continue

        if blurred is None:
            blurred = cv2.GaussianBlur(frame, kernel, 0)

        out[ry1:ry2, rx1:rx2] = blurred[ry1:ry2, rx1:rx2]

    return out
