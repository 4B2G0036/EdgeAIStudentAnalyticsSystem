"""
core/pose_analyzer.py
=====================
High-level Visual AI Pose & Attention Analyzer.

Integrates:
- InferenceEngine (core.inference): pure ONNX inference
- PersonTracker (core.tracker): multi-person tracking with 30-frame occlusion tolerance
- Privacy Filter (core.privacy): Gaussian face/head blur BEFORE drawing overlays
- Head Pose Estimator (core.head_pose): 3-stage Yaw/Pitch geometry
- ROI Filter (core.roi): seat polygon filtering
- Abnormal Pose Deduction: sleeping, phone usage, distraction
- Attention Scoring: [0, 100] per-student and class-wide average
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional, Sequence

import cv2
import numpy as np

import config
from core.models import FrameResult, PoseFlag, TrackedPerson
from core.inference import InferenceEngine
from core.tracker import PersonTracker
from core.privacy import apply_privacy_blur
from core.head_pose import estimate_head_pose
from core.roi import filter_persons_by_roi

logger = logging.getLogger("core.pose_analyzer")

# COCO 17-Keypoint Indices
NOSE = 0
LEFT_EYE = 1
RIGHT_EYE = 2
LEFT_EAR = 3
RIGHT_EAR = 4
LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_ELBOW = 7
RIGHT_ELBOW = 8
LEFT_WRIST = 9
RIGHT_WRIST = 10
LEFT_HIP = 11
RIGHT_HIP = 12
LEFT_KNEE = 13
RIGHT_KNEE = 14
LEFT_ANKLE = 15
RIGHT_ANKLE = 16

# Skeleton connection pairs for drawing
SKELETON_PAIRS = [
    (0, 1), (0, 2), (1, 3), (2, 4),      # Face
    (5, 6),                              # Shoulders
    (5, 7), (7, 9),                      # Left arm
    (6, 8), (8, 10),                     # Right arm
    (5, 11), (6, 12),                    # Torso sides
    (11, 12),                            # Hips
    (11, 13), (13, 15),                  # Left leg
    (12, 14), (14, 16),                  # Right leg
]


class PoseAnalyzer:
    """
    High-level analyzer coordinating the complete Edge AI visual analysis pipeline.
    """

    _instance: Optional["PoseAnalyzer"] = None

    def __init__(self) -> None:
        logger.info("Initializing PoseAnalyzer...")
        self.engine = InferenceEngine.get_instance()
        self.tracker = PersonTracker()

        # Thresholds from config
        self.conf_threshold: float = float(getattr(config, "POSE_CONF_THRESHOLD", 0.35))
        self.sleeping_ratio: float = float(getattr(config, "SLEEPING_RATIO", 0.20))
        self.phone_pitch_thresh: float = float(getattr(config, "PHONE_PITCH_THRESHOLD", -25.0))
        self.board_yaw_thresh: float = float(getattr(config, "BOARD_YAW_THRESHOLD", 30.0))
        self.board_pitch_thresh: float = float(getattr(config, "BOARD_PITCH_THRESHOLD", 25.0))

    @classmethod
    def get_instance(cls) -> "PoseAnalyzer":
        if cls._instance is None:
            cls._instance = PoseAnalyzer()
        return cls._instance

    def _detect_abnormal_pose(
        self,
        kpts: np.ndarray,
        bbox_xyxy: np.ndarray,
        head_yaw: float,
        head_pitch: float,
    ) -> set[PoseFlag]:
        """
        Deduce abnormal posture states according to the official spec:
        - 5.1 Sleeping Detection
        - 5.2 Phone Usage Detection
        - Distraction (looking away from blackboard)
        """
        flags: set[PoseFlag] = set()
        bx1, by1, bx2, by2 = bbox_xyxy
        bbox_h = max(20.0, float(by2 - by1))

        nose = kpts[NOSE]
        lsh = kpts[LEFT_SHOULDER]
        rsh = kpts[RIGHT_SHOULDER]
        lwrist = kpts[LEFT_WRIST]
        rwrist = kpts[RIGHT_WRIST]
        lhip = kpts[LEFT_HIP]
        rhip = kpts[RIGHT_HIP]

        # ── 1. Sleeping Detection ──────────────────────────────────────────────
        # Conditions:
        # A) abs(avg_shoulder_y - nose_y) < SLEEPING_RATIO * bbox_height
        # B) Extreme head pitch tilt (head bowed onto desk or pitch > 60)
        # C) Severe shoulder sideways tilt (> 0.30 * bbox_height)
        is_sleeping = False
        if lsh[2] >= self.conf_threshold and rsh[2] >= self.conf_threshold:
            avg_shoulder_y = (lsh[1] + rsh[1]) / 2.0
            if nose[2] >= self.conf_threshold:
                if abs(avg_shoulder_y - nose[1]) < self.sleeping_ratio * bbox_h:
                    is_sleeping = True

            if head_pitch < -45.0 or head_pitch > 60.0:
                is_sleeping = True

            if abs(lsh[1] - rsh[1]) > 0.30 * bbox_h:
                is_sleeping = True

        if is_sleeping:
            flags.add(PoseFlag.SLEEPING)

        # ── 2. Phone Usage Detection ───────────────────────────────────────────
        # Spec 5.2:
        # 1. Wrist valid (conf > 0.45) AND low (> (avg_shoulder.y + avg_hip.y) / 2)
        #    Note: Spec explicitly states OR condition between left & right wrists
        # 2. Head bowed downward (pitch < -35 or pitch < phone_pitch_thresh)
        is_phone_suspected = False
        avg_sh_y = (lsh[1] + rsh[1]) / 2.0 if (lsh[2] >= self.conf_threshold and rsh[2] >= self.conf_threshold) else (by1 + bbox_h * 0.25)
        avg_hp_y = (lhip[1] + rhip[1]) / 2.0 if (lhip[2] >= self.conf_threshold and rhip[2] >= self.conf_threshold) else (by1 + bbox_h * 0.75)
        mid_torso_y = (avg_sh_y + avg_hp_y) / 2.0

        wrist_low = False
        if lwrist[2] >= 0.40 and lwrist[1] > mid_torso_y:
            wrist_low = True
        elif rwrist[2] >= 0.40 and rwrist[1] > mid_torso_y:
            wrist_low = True

        if wrist_low and (head_pitch < self.phone_pitch_thresh or (nose[2] >= self.conf_threshold and nose[1] > avg_sh_y - 12)):
            if not is_sleeping:
                is_phone_suspected = True
                flags.add(PoseFlag.PHONE_SUSPECTED)

        # ── 3. Distracted Detection (Looking away) ────────────────────────────
        if not is_sleeping and not is_phone_suspected:
            if abs(head_yaw) > self.board_yaw_thresh or abs(head_pitch) > self.board_pitch_thresh:
                flags.add(PoseFlag.DISTRACTED)

        return flags

    def _calculate_score(
        self,
        is_looking: bool,
        flags: set[PoseFlag],
    ) -> float:
        """
        Scoring formula specified in spec:
        - Looking at board: +50
        - Sitting upright (no sleeping): +50
        - Phone suspected penalty: -50
        - Sleeping penalty: -30
        Clamped to [0, 100].
        """
        score = 0.0
        if is_looking and PoseFlag.DISTRACTED not in flags:
            score += 50.0

        if PoseFlag.SLEEPING not in flags:
            score += 50.0

        if PoseFlag.PHONE_SUSPECTED in flags:
            score -= 50.0

        if PoseFlag.SLEEPING in flags:
            score -= 30.0

        return float(max(0.0, min(100.0, score)))

    def analyze(
        self,
        frame: np.ndarray,
        roi_polygon: Optional[Sequence[Sequence[float]]] = None,
        draw_overlay: bool = True,
    ) -> FrameResult:
        """
        Execute full visual analytics pass on a frame according to specification.

        Parameters
        ----------
        frame        : uint8 BGR numpy array
        roi_polygon  : Optional list of normalized [x, y] coordinates
        draw_overlay : Whether to produce privacy-blurred annotated frame

        Returns
        -------
        FrameResult : Complete analytics snapshot
        """
        t0 = time.time()
        frame_id = str(uuid.uuid4())[:8]

        if frame is None or frame.size == 0:
            return FrameResult(
                frame_id=frame_id,
                tracked_persons=[],
                avg_attention_score=100.0,
                active_flags=set(),
                latest_event_desc="等待影像來源",
                inference_ms=0.0,
                annotated_frame=frame,
            )

        h, w = frame.shape[:2]

        # ── Step 1: Forward inference pass (ONNX) ──────────────────────────────
        boxes_xyxy, keypoints, scores, _ = self.engine.infer(frame)
        num_dets = len(boxes_xyxy)
        t_infer = (time.time() - t0) * 1000.0

        if num_dets == 0:
            return FrameResult(
                frame_id=frame_id,
                tracked_persons=[],
                avg_attention_score=100.0,
                active_flags=set(),
                latest_event_desc="未偵測到學生",
                inference_ms=t_infer,
                annotated_frame=frame.copy() if draw_overlay else None,
            )

        # ── Step 2: Multi-person tracking (ByteTrack-like IoU) ─────────────────
        tracking_ids = self.tracker.update(boxes_xyxy)

        # ── Step 3: Analyze each person ────────────────────────────────────────
        tracked_persons: list[TrackedPerson] = []
        for i in range(num_dets):
            tid = tracking_ids[i]
            bbox_px = boxes_xyxy[i]
            kpts = keypoints[i]
            conf = float(scores[i])

            # Normalized bbox (x1, y1, x2, y2) in [0, 1]
            bbox_norm = (
                float(bbox_px[0] / w),
                float(bbox_px[1] / h),
                float(bbox_px[2] / w),
                float(bbox_px[3] / h),
            )

            # Head pose estimation (Yaw / Pitch)
            yaw, pitch, _, is_looking = estimate_head_pose(kpts, tracking_id=tid)

            # Abnormal pose deduction
            pose_flags = self._detect_abnormal_pose(kpts, bbox_px, yaw, pitch)

            # Attention score
            score = self._calculate_score(is_looking, pose_flags)

            person = TrackedPerson(
                tracking_id=tid,
                bbox=bbox_norm,
                keypoints=kpts,
                confidence=conf,
                in_roi=True,
                pose_flags=pose_flags,
                attention_score=score,
                head_yaw=yaw,
                head_pitch=pitch,
                last_seen_at=time.time(),
            )
            tracked_persons.append(person)

        # ── Step 4: ROI Polygon filtering ──────────────────────────────────────
        valid_persons = filter_persons_by_roi(tracked_persons, roi_polygon)

        # Aggregate class metrics
        active_flags: set[PoseFlag] = set()
        latest_event_desc = "姿態標準 (專注聽講)"

        if valid_persons:
            avg_score = float(np.mean([p.attention_score for p in valid_persons]))
            for p in valid_persons:
                active_flags.update(p.pose_flags)

            # Find descriptive event if any
            for p in valid_persons:
                if PoseFlag.SLEEPING in p.pose_flags:
                    latest_event_desc = f"S{p.tracking_id:03d}: 趴睡 (SLEEPING)"
                    break
                elif PoseFlag.PHONE_SUSPECTED in p.pose_flags:
                    latest_event_desc = f"S{p.tracking_id:03d}: 疑似使用手機 (PHONE_SUSPECTED)"
                    break
                elif PoseFlag.DISTRACTED in p.pose_flags:
                    latest_event_desc = f"S{p.tracking_id:03d}: 東張西望 (DISTRACTED)"
        else:
            avg_score = 100.0
            latest_event_desc = "未在座位區偵測到學生"

        # ── Step 5: Privacy Blur & Drawing Overlays ────────────────────────────
        annotated_frame = None
        if draw_overlay:
            # RULE: PII face blurring MUST happen BEFORE drawing labels/skeletons!
            blurred = apply_privacy_blur(frame, boxes_xyxy, keypoints)

            for i in range(num_dets):
                person = tracked_persons[i]
                if not person.in_roi:
                    # Draw ROI-excluded individuals with faded dashed/grey box
                    bx1, by1, bx2, by2 = [int(v) for v in boxes_xyxy[i]]
                    cv2.rectangle(blurred, (bx1, by1), (bx2, by2), (100, 100, 100), 1)
                    continue

                tid = person.tracking_id
                score = person.attention_score
                kpts = person.keypoints
                bx1, by1, bx2, by2 = [int(v) for v in boxes_xyxy[i]]

                # Color-code by attention score
                if score >= 80.0:
                    box_color = (0, 230, 115)     # Vibrant Green
                elif score >= 50.0:
                    box_color = (0, 204, 255)     # Yellow / Gold
                else:
                    box_color = (60, 60, 255)     # Alert Red

                # 1. Draw Bounding Box
                cv2.rectangle(blurred, (bx1, by1), (bx2, by2), box_color, 2)

                # 2. Draw Skeleton Connections
                for p1_idx, p2_idx in SKELETON_PAIRS:
                    pt1 = kpts[p1_idx]
                    pt2 = kpts[p2_idx]
                    if pt1[2] >= self.conf_threshold and pt2[2] >= self.conf_threshold:
                        cv2.line(
                            blurred,
                            (int(pt1[0]), int(pt1[1])),
                            (int(pt2[0]), int(pt2[1])),
                            (0, 240, 255),
                            2,
                            cv2.LINE_AA,
                        )

                # 3. Draw Keypoints
                for pt in kpts:
                    if pt[2] >= self.conf_threshold:
                        cv2.circle(
                            blurred,
                            (int(pt[0]), int(pt[1])),
                            3,
                            (0, 165, 255),
                            -1,
                            cv2.LINE_AA,
                        )

                # 4. Draw Label Tag with solid dark background
                tag_label = f"S{tid:03d} | {int(score)}分"
                if PoseFlag.SLEEPING in person.pose_flags:
                    tag_label += " [趴睡]"
                elif PoseFlag.PHONE_SUSPECTED in person.pose_flags:
                    tag_label += " [手機]"
                elif PoseFlag.DISTRACTED in person.pose_flags:
                    tag_label += " [分心]"

                label_y = max(24, by1 - 6)
                (tw, th), _ = cv2.getTextSize(tag_label, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
                cv2.rectangle(blurred, (bx1, label_y - th - 4), (bx1 + tw + 8, label_y + 4), (20, 24, 33), -1)
                cv2.putText(
                    blurred,
                    tag_label,
                    (bx1 + 4, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.52,
                    box_color,
                    2,
                    cv2.LINE_AA,
                )

            annotated_frame = blurred

        return FrameResult(
            frame_id=frame_id,
            tracked_persons=valid_persons,
            avg_attention_score=round(avg_score, 1),
            active_flags=active_flags,
            latest_event_desc=latest_event_desc,
            inference_ms=round(t_infer, 1),
            annotated_frame=annotated_frame,
            timestamp=time.time(),
        )

    def analyze_frame(
        self,
        frame: np.ndarray,
        roi_polygon: Optional[Sequence[Sequence[float]]] = None,
        draw_overlay: bool = True,
    ) -> dict:
        """
        Backwards-compatible dictionary wrapper around analyze().
        Directly satisfies API callers (stream.py, realtime.py).
        """
        res = self.analyze(frame, roi_polygon=roi_polygon, draw_overlay=draw_overlay)

        return {
            "student_count": res.student_count,
            "attention_score": res.avg_attention_score,
            "latest_event": res.latest_event_desc,
            "events": res.events,
            "annotated_frame": res.annotated_frame,
            "inference_ms": res.inference_ms,
            "tracked_persons": res.tracked_persons,
            "frame_result": res,
        }
