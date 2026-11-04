"""
core/head_pose.py
=================
Three-stage head-pose estimation (Yaw / Pitch in degrees).

Strategy priority (per spec):
  1. Nose + Left Eye + Right Eye  (all conf ≥ threshold) → geometric Yaw/Pitch
  2. Left Ear + Right Ear [+ Shoulders] (all conf ≥ threshold) → ear-shoulder auxiliary
  3. Shoulders only (both conf ≥ threshold) → shoulder-line Yaw, Pitch = 0
  0. None visible → return (0, 0, 0, True)   [fallback, treated as "looking OK"]

"Looking at board" condition: |Yaw| ≤ BOARD_YAW_THRESHOLD AND |Pitch| ≤ BOARD_PITCH_THRESHOLD
"""
from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np

import config

logger = logging.getLogger("core.head_pose")

# ── COCO Keypoint indices ──────────────────────────────────────────────────────
NOSE         = 0
LEFT_EYE     = 1
RIGHT_EYE    = 2
LEFT_EAR     = 3
RIGHT_EAR    = 4
LEFT_SHOULDER  = 5
RIGHT_SHOULDER = 6

# ── Config thresholds ──────────────────────────────────────────────────────────
def _get_conf_thresh() -> float:
    return float(getattr(config, "POSE_CONF_THRESHOLD", 0.35))

def _get_yaw_thresh() -> float:
    return float(getattr(config, "BOARD_YAW_THRESHOLD", 30.0))

def _get_pitch_thresh() -> float:
    return float(getattr(config, "BOARD_PITCH_THRESHOLD", 25.0))

def _get_pitch_offset() -> float:
    ceiling = getattr(config, "CAMERA_CEILING_MODE", True)
    default_offset = 35.0 if ceiling else 20.0
    return float(getattr(config, "CAMERA_PITCH_OFFSET", default_offset))


def estimate_head_pose(
    keypoints: np.ndarray,   # (17, 3)  (x_px, y_px, conf)
    tracking_id: int = -1,
) -> tuple[float, float, int, bool]:
    """
    Estimate Yaw and Pitch angles for a single person.
    Optimized for ceiling-mounted (overhead / high-angle) classroom cameras.

    Parameters
    ----------
    keypoints   : (17, 3) float32 array – COCO keypoints in pixel space
    tracking_id : for debug logging only

    Returns
    -------
    yaw         : float  degrees, positive = turned right
    pitch       : float  degrees, positive = tilted up, negative = tilted down
    strategy    : int    1/2/3 which calculation strategy was used; 0 = fallback
    is_looking  : bool   True if head is oriented toward the board
    """
    conf_thresh = _get_conf_thresh()
    yaw_thresh = _get_yaw_thresh()
    pitch_thresh = _get_pitch_thresh()
    pitch_offset = _get_pitch_offset()

    def _valid(idx: int) -> bool:
        return bool(keypoints[idx, 2] >= conf_thresh)

    nose  = keypoints[NOSE]
    leye  = keypoints[LEFT_EYE]
    reye  = keypoints[RIGHT_EYE]
    lear  = keypoints[LEFT_EAR]
    rear  = keypoints[RIGHT_EAR]
    lsh   = keypoints[LEFT_SHOULDER]
    rsh   = keypoints[RIGHT_SHOULDER]

    # ── Strategy 1: Nose + Eyes ────────────────────────────────────────────────
    if _valid(NOSE) and _valid(LEFT_EYE) and _valid(RIGHT_EYE):
        eye_mid_x = (leye[0] + reye[0]) / 2.0
        eye_mid_y = (leye[1] + reye[1]) / 2.0
        eye_dist  = max(8.0, math.hypot(reye[0] - leye[0], reye[1] - leye[1]))

        # Yaw: horizontal displacement of nose vs eye midpoint
        # When student looks left, nose shifts left of eye-mid → negative yaw
        yaw   = ((nose[0] - eye_mid_x) / eye_dist) * 60.0

        # Pitch: in image coords y↓, so "looking down" means nose_y > eye_mid_y
        # Positive pitch = looking up (nose above eye midpoint in image space)
        # 天花板俯角補償：攝影機由高處向下拍，學生往前看黑板時鼻孔投影自然低於眼睛，
        # 加上 pitch_offset (預設天花板模式 +35°，水平鏡頭 +20°) 校正為真實水平視線。
        pitch_scale = eye_dist
        if _valid(LEFT_SHOULDER) and _valid(RIGHT_SHOULDER):
            shoulder_w = math.hypot(rsh[0] - lsh[0], rsh[1] - lsh[1])
            pitch_scale = max(eye_dist, 0.22 * shoulder_w)
        pitch = ((eye_mid_y - nose[1]) / pitch_scale) * 60.0 + pitch_offset

        # 限制合理範圍，避免關鍵點抖動產生極端數值
        yaw = max(-90.0, min(90.0, float(yaw)))
        pitch = max(-90.0, min(90.0, float(pitch)))
        is_looking = abs(yaw) <= yaw_thresh and abs(pitch) <= pitch_thresh
        logger.debug("ID=%d  Strategy=1  yaw=%.1f  pitch=%.1f  looking=%s",
                     tracking_id, yaw, pitch, is_looking)
        return yaw, pitch, 1, is_looking

    # ── Strategy 2: Ears (+ optional shoulders for lateral reference) ──────────
    if _valid(LEFT_EAR) and _valid(RIGHT_EAR):
        ear_mid_x = (lear[0] + rear[0]) / 2.0
        ear_dist  = max(10.0, math.hypot(rear[0] - lear[0], rear[1] - lear[1]))

        # Use shoulder mid as lateral reference if available
        if _valid(LEFT_SHOULDER) and _valid(RIGHT_SHOULDER):
            sh_mid_x = (lsh[0] + rsh[0]) / 2.0
        else:
            sh_mid_x = ear_mid_x   # no shoulder reference → assume facing forward

        yaw   = float(((ear_mid_x - sh_mid_x) / ear_dist) * 45.0)
        pitch = 0.0   # cannot infer pitch from ears alone

        is_looking = abs(yaw) <= yaw_thresh
        logger.debug("ID=%d  Strategy=2 (ears)  yaw=%.1f  looking=%s",
                     tracking_id, yaw, is_looking)
        return yaw, pitch, 2, is_looking

    # ── Strategy 3: Shoulders only → Yaw from shoulder tilt ───────────────────
    if _valid(LEFT_SHOULDER) and _valid(RIGHT_SHOULDER):
        dx = float(rsh[0] - lsh[0])
        dy = float(rsh[1] - lsh[1])
        # Angle of shoulder line relative to horizontal
        yaw   = float(math.degrees(math.atan2(dy, dx)))
        pitch = 0.0

        is_looking = abs(yaw) <= yaw_thresh * 0.85   # slightly stricter for shoulder-only
        logger.debug("ID=%d  Strategy=3 (shoulders)  yaw=%.1f  looking=%s",
                     tracking_id, yaw, is_looking)
        return yaw, pitch, 3, is_looking

    # ── Fallback ───────────────────────────────────────────────────────────────
    logger.debug("ID=%d  No valid head/shoulder keypoints – returning fallback.", tracking_id)
    return 0.0, 0.0, 0, True
