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
import math
import threading
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
from core.drawing import draw_labels_bgr

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
        self.sleeping_ratio: float = float(getattr(config, "SLEEPING_RATIO", 0.12))
        self.phone_pitch_thresh: float = float(getattr(config, "PHONE_PITCH_THRESHOLD", -30.0))
        self.board_yaw_thresh: float = float(getattr(config, "BOARD_YAW_THRESHOLD", 30.0))
        self.board_pitch_thresh: float = float(getattr(config, "BOARD_PITCH_THRESHOLD", 25.0))

        # Hand action & gesture thresholds (ceiling camera optimized)
        self.hand_raise_ratio: float = float(getattr(config, "HAND_RAISE_OFFSET_RATIO", 0.18))
        self.hand_support_ratio: float = float(getattr(config, "HAND_SUPPORT_DIST_RATIO", 0.38))
        self.phone_cluster_ratio: float = float(getattr(config, "PHONE_HAND_CLUSTER_RATIO", 0.55))
        self.phone_midline_ratio: float = float(getattr(config, "PHONE_MIDLINE_RATIO", 0.45))

        # Sleeping detection tuning (strict evidence + temporal filtering)
        self.sleeping_pitch_low: float = float(getattr(config, "SLEEPING_PITCH_LOW", -60.0))
        self.sleeping_pitch_high: float = float(getattr(config, "SLEEPING_PITCH_HIGH", 70.0))
        self.sleeping_tilt_ratio: float = float(getattr(config, "SLEEPING_SHOULDER_TILT_RATIO", 0.45))
        self.sleeping_confirm_frames: int = max(1, int(getattr(config, "SLEEPING_CONFIRM_FRAMES", 6)))
        self.sleeping_release_frames: int = max(1, int(getattr(config, "SLEEPING_RELEASE_FRAMES", 3)))

        # Per-track sleeping debounce state: tid -> {"on": int, "off": int, "active": bool, "seen": int}
        self._sleep_state: dict[int, dict] = {}
        self._sleep_lock = threading.Lock()
        self._frame_no: int = 0

    @classmethod
    def get_instance(cls) -> "PoseAnalyzer":
        if cls._instance is None:
            cls._instance = PoseAnalyzer()
        return cls._instance

    def _debounce_sleeping(self, tracking_id: Optional[int], raw_sleeping: bool) -> bool:
        """
        Temporal filter for the sleeping verdict (per tracked student).

        - 連續 `sleeping_confirm_frames` 幀都符合才確認趴睡 (避免低頭撿東西、短暫抖動誤判)
        - 已確認後，連續 `sleeping_release_frames` 幀都不符合才解除 (避免閃爍)
        - tracking_id 為 None (直接呼叫/單元測試) 時不做時間濾波，直接回傳原始判斷
        """
        if tracking_id is None:
            return raw_sleeping

        with self._sleep_lock:
            st = self._sleep_state.get(tracking_id)
            if st is None:
                st = {"on": 0, "off": 0, "active": False, "seen": self._frame_no}
                self._sleep_state[tracking_id] = st
            st["seen"] = self._frame_no

            if raw_sleeping:
                st["on"] += 1
                st["off"] = 0
                if not st["active"] and st["on"] >= self.sleeping_confirm_frames:
                    st["active"] = True
            else:
                st["off"] += 1
                st["on"] = 0
                if st["active"] and st["off"] >= self.sleeping_release_frames:
                    st["active"] = False
            return bool(st["active"])

    def _prune_sleep_state(self, max_idle_frames: int = 60) -> None:
        """Drop debounce state of tracks that have not been seen for a while."""
        with self._sleep_lock:
            stale = [tid for tid, st in self._sleep_state.items()
                     if self._frame_no - st["seen"] > max_idle_frames]
            for tid in stale:
                del self._sleep_state[tid]

    def _detect_abnormal_pose(
        self,
        kpts: np.ndarray,
        bbox_xyxy: np.ndarray,
        head_yaw: float,
        head_pitch: float,
        tracking_id: Optional[int] = None,
    ) -> set[PoseFlag]:
        """
        Deduce abnormal and engagement posture states optimized for ceiling-mounted cameras:
        - 1. Sleeping Detection (head near desk or face buried in desk)
        - 2. Hand Raised (positive classroom engagement / questions)
        - 3. Chin / Head Support (fatigue / boredom)
        - 4. Phone Usage (hands clustered or deep lap gaze; excludes normal desk writing)
        - 5. Distraction (looking away from blackboard)
        """
        flags: set[PoseFlag] = set()
        bx1, by1, bx2, by2 = bbox_xyxy
        bbox_w = max(20.0, float(bx2 - bx1))
        bbox_h = max(20.0, float(by2 - by1))

        nose = kpts[NOSE]
        leye = kpts[LEFT_EYE]
        reye = kpts[RIGHT_EYE]
        lear = kpts[LEFT_EAR]
        rear = kpts[RIGHT_EAR]
        lsh = kpts[LEFT_SHOULDER]
        rsh = kpts[RIGHT_SHOULDER]
        lwrist = kpts[LEFT_WRIST]
        rwrist = kpts[RIGHT_WRIST]
        lhip = kpts[LEFT_HIP]
        rhip = kpts[RIGHT_HIP]

        # ── 1. Sleeping Detection ──────────────────────────────────────────────
        raw_sleeping = False
        if lsh[2] >= self.conf_threshold and rsh[2] >= self.conf_threshold:
            avg_shoulder_y = (lsh[1] + rsh[1]) / 2.0

            head_on_shoulder_line = (
                nose[2] >= self.conf_threshold
                and abs(avg_shoulder_y - nose[1]) < self.sleeping_ratio * bbox_h
            )
            # 天花板俯視埋頭趴睡輔助特徵：面部朝下埋於桌面/手臂 (五官遮蔽但耳朵/肩線可見)
            ear_buried = False
            if nose[2] < self.conf_threshold:
                valid_ears = [pt for pt in [lear, rear] if pt[2] >= self.conf_threshold]
                if valid_ears:
                    ear_y = float(np.mean([pt[1] for pt in valid_ears]))
                    if abs(ear_y - avg_shoulder_y) < self.sleeping_ratio * bbox_h:
                        ear_buried = True

            extreme_pitch = (
                head_pitch < self.sleeping_pitch_low or head_pitch > self.sleeping_pitch_high
            )
            severe_shoulder_tilt = abs(lsh[1] - rsh[1]) > self.sleeping_tilt_ratio * bbox_h

            raw_sleeping = head_on_shoulder_line or ear_buried or (extreme_pitch and severe_shoulder_tilt)

        is_sleeping = self._debounce_sleeping(tracking_id, raw_sleeping)
        if is_sleeping:
            flags.add(PoseFlag.SLEEPING)

        # ── 2. Hand Action: Hand Raised (舉手發問 / 伸展互動) ────────────────────
        # 舉手：手腕需高於眼睛高度，或高於肩線超過 (hand_raise_ratio × bbox_h)
        eye_y = (
            min(leye[1], reye[1])
            if (leye[2] >= 0.35 and reye[2] >= 0.35)
            else (nose[1] if nose[2] >= 0.35 else (by1 + bbox_h * 0.20))
        )
        sh_top_y = (
            min(lsh[1], rsh[1])
            if (lsh[2] >= self.conf_threshold and rsh[2] >= self.conf_threshold)
            else (by1 + bbox_h * 0.30)
        )
        hand_raise_thresh_y = min(eye_y + 10.0, sh_top_y - self.hand_raise_ratio * bbox_h)

        is_hand_raised = False
        if (lwrist[2] >= 0.35 and lwrist[1] < hand_raise_thresh_y) or \
           (rwrist[2] >= 0.35 and rwrist[1] < hand_raise_thresh_y):
            is_hand_raised = True
            flags.add(PoseFlag.HAND_RAISED)

        # ── 3. Hand Action: Chin / Head Support (托腮撐頭) ───────────────────────
        is_head_support = False
        if not is_sleeping and not is_hand_raised:
            shoulder_w = (
                math.hypot(rsh[0] - lsh[0], rsh[1] - lsh[1])
                if (lsh[2] >= self.conf_threshold and rsh[2] >= self.conf_threshold)
                else (bbox_w * 0.6)
            )
            head_anchors = [pt for pt in [nose, lear, rear, leye, reye] if pt[2] >= 0.35]
            if head_anchors:
                for wrist in (lwrist, rwrist):
                    if wrist[2] >= 0.35:
                        # 手腕需位於肩線附近或上方
                        max_wrist_y = (
                            max(lsh[1], rsh[1]) + 0.10 * bbox_h
                            if (lsh[2] >= self.conf_threshold and rsh[2] >= self.conf_threshold)
                            else (by1 + bbox_h * 0.40)
                        )
                        if wrist[1] < max_wrist_y:
                            min_dist = min(math.hypot(wrist[0] - a[0], wrist[1] - a[1]) for a in head_anchors)
                            if min_dist < self.hand_support_ratio * shoulder_w:
                                is_head_support = True
                                flags.add(PoseFlag.HEAD_SUPPORT)
                                break

        # ── 4. Phone Usage Detection (疑似滑手機 - 天花板防誤判) ───────────────────
        is_phone_suspected = False
        if not is_sleeping and not is_hand_raised:
            avg_sh_y = (lsh[1] + rsh[1]) / 2.0 if (lsh[2] >= self.conf_threshold and rsh[2] >= self.conf_threshold) else (by1 + bbox_h * 0.25)
            avg_hp_y = (lhip[1] + rhip[1]) / 2.0 if (lhip[2] >= self.conf_threshold and rhip[2] >= self.conf_threshold) else (by1 + bbox_h * 0.75)
            mid_torso_y = (avg_sh_y + avg_hp_y) / 2.0
            shoulder_w = (
                math.hypot(rsh[0] - lsh[0], rsh[1] - lsh[1])
                if (lsh[2] >= self.conf_threshold and rsh[2] >= self.conf_threshold)
                else (bbox_w * 0.6)
            )

            both_wrists_visible = (lwrist[2] >= 0.35 and rwrist[2] >= 0.35)
            wrist_dist = math.hypot(lwrist[0] - rwrist[0], lwrist[1] - rwrist[1]) if both_wrists_visible else 999.0
            hands_clustered = both_wrists_visible and (wrist_dist < self.phone_cluster_ratio * shoulder_w)

            wrist_low = False
            if lwrist[2] >= 0.35 and lwrist[1] > mid_torso_y:
                wrist_low = True
            elif rwrist[2] >= 0.35 and rwrist[1] > mid_torso_y:
                wrist_low = True

            # 書寫/桌面上雙手展開排除
            writing_or_desk_spread = both_wrists_visible and (wrist_dist >= self.phone_cluster_ratio * shoulder_w)

            # 模式 A: 雙手在胸前/桌下聚攏持手機操作
            if hands_clustered and (head_pitch < -18.0 or (nose[2] >= self.conf_threshold and nose[1] > avg_sh_y - 12)):
                is_phone_suspected = True
            # 模式 B: 單手放腿上/抽屜滑手機 (手腕低於軀幹且低頭深傾)
            elif wrist_low and not writing_or_desk_spread:
                if head_pitch < self.phone_pitch_thresh or (nose[2] >= self.conf_threshold and nose[1] > avg_sh_y - 12):
                    is_phone_suspected = True

            if is_phone_suspected:
                flags.add(PoseFlag.PHONE_SUSPECTED)

        # ── 5. Distracted Detection (Looking away) ────────────────────────────
        if not is_sleeping and not is_phone_suspected and not is_hand_raised:
            if abs(head_yaw) > self.board_yaw_thresh or abs(head_pitch) > self.board_pitch_thresh:
                flags.add(PoseFlag.DISTRACTED)

        return flags

    def _calculate_score(
        self,
        is_looking: bool,
        flags: set[PoseFlag],
    ) -> float:
        """
        Scoring formula:
        - Looking at board: +50
        - Sitting upright (no sleeping): +50
        - Phone suspected penalty: -50
        - Sleeping penalty: -30
        - Head support penalty: -15
        - Hand raised: keeps full 100 (actively engaging)
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

        if PoseFlag.HEAD_SUPPORT in flags:
            score -= 15.0

        if PoseFlag.HAND_RAISED in flags:
            score = max(score, 100.0)

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

        # 推進影格序號並清理久未出現之追蹤 ID 的趴睡濾波狀態
        self._frame_no += 1
        if self._frame_no % 30 == 0:
            self._prune_sleep_state()
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
            pose_flags = self._detect_abnormal_pose(kpts, bbox_px, yaw, pitch, tracking_id=tid)

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
                    break
                elif PoseFlag.HEAD_SUPPORT in p.pose_flags:
                    latest_event_desc = f"S{p.tracking_id:03d}: 托腮撐頭 (HEAD_SUPPORT)"
                    break
                elif PoseFlag.HAND_RAISED in p.pose_flags:
                    latest_event_desc = f"S{p.tracking_id:03d}: 舉手發問 (HAND_RAISED)"
                    break
        else:
            avg_score = 100.0
            latest_event_desc = "未在座位區偵測到學生"

        # ── Step 5: Privacy Blur & Drawing Overlays ────────────────────────────
        annotated_frame = None
        if draw_overlay:
            # RULE: PII face blurring MUST happen BEFORE drawing labels/skeletons!
            blurred = apply_privacy_blur(frame, boxes_xyxy, keypoints)
            label_items: list[dict] = []

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

                # Color-code by posture and attention score
                if PoseFlag.SLEEPING in person.pose_flags or PoseFlag.PHONE_SUSPECTED in person.pose_flags:
                    box_color = (60, 60, 255)     # Alert Red
                elif PoseFlag.DISTRACTED in person.pose_flags:
                    box_color = (0, 140, 255)     # Orange
                elif PoseFlag.HEAD_SUPPORT in person.pose_flags:
                    box_color = (0, 204, 255)     # Soft Gold / Amber
                elif PoseFlag.HAND_RAISED in person.pose_flags:
                    box_color = (255, 220, 0)     # Vibrant Cyan
                elif score >= 80.0:
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

                # 4. Hand Action Visual Highlights
                if PoseFlag.HAND_RAISED in person.pose_flags:
                    sh_y = min(kpts[LEFT_SHOULDER, 1], kpts[RIGHT_SHOULDER, 1])
                    for w_idx in (LEFT_WRIST, RIGHT_WRIST):
                        wpt = kpts[w_idx]
                        if wpt[2] >= 0.35 and wpt[1] < sh_y:
                            wx, wy = int(wpt[0]), int(wpt[1])
                            cv2.circle(blurred, (wx, wy), 12, (255, 220, 0), 2, cv2.LINE_AA)
                            cv2.circle(blurred, (wx, wy), 4, (255, 255, 255), -1, cv2.LINE_AA)
                elif PoseFlag.PHONE_SUSPECTED in person.pose_flags:
                    lw = kpts[LEFT_WRIST]
                    rw = kpts[RIGHT_WRIST]
                    if lw[2] >= 0.35 and rw[2] >= 0.35:
                        cv2.line(blurred, (int(lw[0]), int(lw[1])), (int(rw[0]), int(rw[1])), (60, 60, 255), 2, cv2.LINE_AA)
                        cv2.circle(blurred, (int(lw[0]), int(lw[1])), 5, (60, 60, 255), -1)
                        cv2.circle(blurred, (int(rw[0]), int(rw[1])), 5, (60, 60, 255), -1)
                elif PoseFlag.HEAD_SUPPORT in person.pose_flags:
                    for w_idx in (LEFT_WRIST, RIGHT_WRIST):
                        wpt = kpts[w_idx]
                        if wpt[2] >= 0.35 and wpt[1] < (kpts[LEFT_SHOULDER, 1] + 15):
                            cv2.circle(blurred, (int(wpt[0]), int(wpt[1])), 9, (0, 204, 255), 2, cv2.LINE_AA)

                # 5. Prepare Label Tag with solid dark background
                tag_label = f"S{tid:03d} | {int(score)}分"
                if PoseFlag.SLEEPING in person.pose_flags:
                    tag_label += " [趴睡]"
                elif PoseFlag.PHONE_SUSPECTED in person.pose_flags:
                    tag_label += " [手機]"
                elif PoseFlag.DISTRACTED in person.pose_flags:
                    tag_label += " [分心]"
                elif PoseFlag.HEAD_SUPPORT in person.pose_flags:
                    tag_label += " [托腮]"
                elif PoseFlag.HAND_RAISED in person.pose_flags:
                    tag_label += " [舉手]"
                else:
                    tag_label += " [專注]"

                # Position label tag: place above bbox, or inside top if near frame/banner edge
                if by1 >= 60:
                    tag_org = (bx1, by1 - 22)
                else:
                    tag_org = (bx1 + 4, max(38, by1 + 4))

                label_items.append({
                    "text": tag_label,
                    "org": tag_org,
                    "font_size": 14,
                    "color_bgr": box_color,
                    "bg_color_bgr": (20, 24, 33),
                    "padding": (5, 3),
                    "bold": True,
                })

            if label_items:
                draw_labels_bgr(blurred, label_items)

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
