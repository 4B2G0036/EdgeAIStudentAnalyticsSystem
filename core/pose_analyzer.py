import os
import cv2
import time
import math
import logging
import numpy as np
from datetime import datetime
from ultralytics import YOLO
import config

logger = logging.getLogger("core.pose_analyzer")

# Keypoint indices according to COCO 17-keypoint standard
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
    (0, 1), (0, 2), (1, 3), (2, 4), # face
    (5, 6), # shoulders
    (5, 7), (7, 9), # left arm
    (6, 8), (8, 10), # right arm
    (5, 11), (6, 12), # torso
    (11, 12), # hips
    (11, 13), (13, 15), # left leg
    (12, 14), (14, 16)  # right leg
]

class PoseAnalyzer:
    _instance = None

    def __init__(self):
        # Prefer onnx model if available, fallback to pt
        onnx_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "yolov8n-pose.onnx")
        pt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "yolov8n-pose.pt")
        
        if os.path.exists(onnx_path):
            model_target = onnx_path
        elif os.path.exists(pt_path):
            model_target = pt_path
        else:
            model_target = "yolov8n-pose.pt"
            
        logger.info(f"Loading YOLO-Pose model from: {model_target}")
        self.model = YOLO(model_target)
        self.conf_threshold = getattr(config, "POSE_CONF_THRESHOLD", 0.35)
        self.sleeping_ratio = getattr(config, "SLEEPING_RATIO", 0.20)
        self.phone_pitch_threshold = getattr(config, "PHONE_PITCH_THRESHOLD", -25.0)
        
        # Track persistent FSM / alert state per student
        self.student_states = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PoseAnalyzer()
        return cls._instance

    def _estimate_head_pose(self, keypoints, bbox):
        """
        Estimate Yaw and Pitch angles based on face/shoulder keypoints.
        Returns: (yaw, pitch, strategy, is_looking_at_board)
        """
        # Strategy 1: Nose, Left Eye, Right Eye
        nose = keypoints[NOSE]
        leye = keypoints[LEFT_EYE]
        reye = keypoints[RIGHT_EYE]

        if nose[2] >= self.conf_threshold and leye[2] >= self.conf_threshold and reye[2] >= self.conf_threshold:
            eye_mid_x = (leye[0] + reye[0]) / 2.0
            eye_mid_y = (leye[1] + reye[1]) / 2.0
            eye_dist = max(10.0, math.hypot(reye[0] - leye[0], reye[1] - leye[1]))
            
            # Yaw: horizontal displacement of nose relative to eye midpoint
            yaw = ((nose[0] - eye_mid_x) / eye_dist) * 60.0
            # Pitch: vertical displacement (negative = looking down, positive = looking up)
            # In image coords, y increases downwards, so nose_y > eye_mid_y is normal
            # If nose drops significantly lower than normal eye-nose distance => looking down
            pitch = ((eye_mid_y - nose[1]) / eye_dist) * 60.0 + 20.0
            
            is_looking = abs(yaw) <= 32.0 and abs(pitch) <= 30.0
            return float(yaw), float(pitch), 1, is_looking

        # Strategy 2: Ears + Shoulders
        lear = keypoints[LEFT_EAR]
        rear = keypoints[RIGHT_EAR]
        lsh = keypoints[LEFT_SHOULDER]
        rsh = keypoints[RIGHT_SHOULDER]

        if lear[2] >= self.conf_threshold and rear[2] >= self.conf_threshold:
            ear_mid_x = (lear[0] + rear[0]) / 2.0
            sh_mid_x = (lsh[0] + rsh[0]) / 2.0 if (lsh[2] >= self.conf_threshold and rsh[2] >= self.conf_threshold) else ear_mid_x
            sh_dist = max(20.0, math.hypot(rear[0] - lear[0], rear[1] - lear[1]))
            yaw = ((ear_mid_x - sh_mid_x) / sh_dist) * 45.0
            pitch = 0.0
            is_looking = abs(yaw) <= 30.0
            return float(yaw), float(pitch), 2, is_looking

        # Strategy 3: Shoulders only
        if lsh[2] >= self.conf_threshold and rsh[2] >= self.conf_threshold:
            dx = rsh[0] - lsh[0]
            dy = rsh[1] - lsh[1]
            yaw = math.degrees(math.atan2(dy, dx))
            pitch = 0.0
            is_looking = abs(yaw) <= 25.0
            return float(yaw), float(pitch), 3, is_looking

        return 0.0, 0.0, 0, True

    def _detect_abnormal_pose(self, keypoints, bbox, yaw, pitch):
        """
        Evaluate if person is sleeping or suspected of using a phone.
        Returns: (is_sleeping, is_phone_suspected, is_distracted, flag_str)
        """
        x1, y1, x2, y2 = bbox
        bbox_height = max(20.0, y2 - y1)
        
        nose = keypoints[NOSE]
        lsh = keypoints[LEFT_SHOULDER]
        rsh = keypoints[RIGHT_SHOULDER]
        lwrist = keypoints[LEFT_WRIST]
        rwrist = keypoints[RIGHT_WRIST]
        lhip = keypoints[LEFT_HIP]
        rhip = keypoints[RIGHT_HIP]
        
        is_sleeping = False
        is_phone_suspected = False
        is_distracted = False
        
        # 1. Sleeping detection
        if lsh[2] >= self.conf_threshold and rsh[2] >= self.conf_threshold:
            avg_shoulder_y = (lsh[1] + rsh[1]) / 2.0
            # Condition A: Nose very close to shoulders (head dropped to desk)
            if nose[2] >= self.conf_threshold:
                if abs(avg_shoulder_y - nose[1]) < self.sleeping_ratio * bbox_height:
                    is_sleeping = True
            # Condition B: Extreme downward head tilt
            if pitch < -45.0 or pitch > 65.0:
                is_sleeping = True
            # Condition C: Heavily tilted shoulders (lying sideways)
            if abs(lsh[1] - rsh[1]) > 0.30 * bbox_height:
                is_sleeping = True

        # 2. Phone usage detection
        # Hand/wrist low while head pitch is distinctly downwards
        has_wrist = False
        wrist_low = False
        
        # Calculate mid torso line
        shoulder_y = (lsh[1] + rsh[1]) / 2.0 if (lsh[2] >= self.conf_threshold and rsh[2] >= self.conf_threshold) else (y1 + bbox_height * 0.25)
        hip_y = (lhip[1] + rhip[1]) / 2.0 if (lhip[2] >= self.conf_threshold and rhip[2] >= self.conf_threshold) else (y1 + bbox_height * 0.75)
        mid_torso_y = (shoulder_y + hip_y) / 2.0
        
        if lwrist[2] >= self.conf_threshold and lwrist[1] > mid_torso_y:
            has_wrist = True
            wrist_low = True
        elif rwrist[2] >= self.conf_threshold and rwrist[1] > mid_torso_y:
            has_wrist = True
            wrist_low = True

        # Pitch downwards or head bowed
        if wrist_low and (pitch < -20.0 or (nose[2] >= self.conf_threshold and nose[1] > shoulder_y - 15)):
            if not is_sleeping:
                is_phone_suspected = True

        # 3. Distracted detection (Looking away from board)
        if not is_sleeping and not is_phone_suspected and abs(yaw) > 35.0:
            is_distracted = True

        flag_str = ""
        if is_sleeping:
            flag_str = "趴睡 (SLEEPING)"
        elif is_phone_suspected:
            flag_str = "疑似使用手機 (PHONE_SUSPECTED)"
        elif is_distracted:
            flag_str = "東張西望/分心 (DISTRACTED)"

        return is_sleeping, is_phone_suspected, is_distracted, flag_str

    def _calculate_score(self, is_looking, is_sleeping, is_phone_suspected):
        """
        Scoring formula specified in spec:
        - Looking at board: +50
        - Sitting upright (no sleeping): +50
        - Phone suspected penalty: -50
        - Sleeping penalty: -30
        Clamped to [0, 100]
        """
        score = 0
        if is_looking:
            score += 50
        if not is_sleeping:
            score += 50
            
        if is_phone_suspected:
            score -= 50
        if is_sleeping:
            score -= 30

        return max(0, min(100, score))

    def analyze_frame(self, frame: np.ndarray, draw_overlay: bool = True) -> dict:
        """
        Run YOLOv8-Pose on frame and compute real-time analytics.
        Returns:
            student_count: int
            attention_score: float (0.0 - 100.0)
            latest_event: str
            events: list of str
            annotated_frame: np.ndarray (if draw_overlay is True)
        """
        if frame is None or frame.size == 0:
            return {
                "student_count": 0,
                "attention_score": 100.0,
                "latest_event": "等待影像來源",
                "events": [],
                "annotated_frame": frame
            }

        try:
            results = self.model(frame, verbose=False)
            res = results[0]
        except Exception as e:
            logger.error(f"Inference failed: {e}")
            return {
                "student_count": 0,
                "attention_score": 100.0,
                "latest_event": "AI 推論異常",
                "events": [],
                "annotated_frame": frame
            }

        boxes = res.boxes
        keypoints_obj = res.keypoints

        if boxes is None or len(boxes) == 0:
            return {
                "student_count": 0,
                "attention_score": 100.0,
                "latest_event": "未偵測到學生",
                "events": [],
                "annotated_frame": frame
            }

        num_persons = len(boxes)
        kpts_data = keypoints_obj.data.cpu().numpy() if keypoints_obj is not None else []
        boxes_xyxy = boxes.xyxy.cpu().numpy()

        scores = []
        events = []
        latest_event = ""

        out_frame = frame.copy() if draw_overlay else frame

        for i in range(num_persons):
            student_id = f"S{i+1:03d}"
            bbox = boxes_xyxy[i]
            kpts = kpts_data[i] if i < len(kpts_data) else np.zeros((17, 3))

            yaw, pitch, strategy, is_looking = self._estimate_head_pose(kpts, bbox)
            is_sleeping, is_phone, is_distracted, flag_str = self._detect_abnormal_pose(kpts, bbox, yaw, pitch)
            score = self._calculate_score(is_looking, is_sleeping, is_phone)
            scores.append(score)

            if flag_str:
                event_desc = f"{student_id}: {flag_str}"
                events.append(event_desc)
                latest_event = event_desc

            # Overlay drawing
            if draw_overlay:
                x1, y1, x2, y2 = [int(v) for v in bbox]
                # Box color based on score
                if score >= 80:
                    color = (0, 230, 115) # Green
                elif score >= 50:
                    color = (0, 204, 255) # Yellow/Cyan
                else:
                    color = (50, 50, 255) # Red

                cv2.rectangle(out_frame, (x1, y1), (x2, y2), color, 2)
                
                # Draw skeleton connections
                for pt1_idx, pt2_idx in SKELETON_PAIRS:
                    pt1 = kpts[pt1_idx]
                    pt2 = kpts[pt2_idx]
                    if pt1[2] >= self.conf_threshold and pt2[2] >= self.conf_threshold:
                        cv2.line(out_frame, (int(pt1[0]), int(pt1[1])), (int(pt2[0]), int(pt2[1])), (0, 255, 255), 2)

                # Draw keypoints
                for pt in kpts:
                    if pt[2] >= self.conf_threshold:
                        cv2.circle(out_frame, (int(pt[0]), int(pt[1])), 3, (0, 165, 255), -1)

                # Label tag
                tag = f"{student_id} | {score}分"
                if flag_str:
                    tag += f" [{flag_str.split(' ')[0]}]"
                cv2.putText(out_frame, tag, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        avg_score = float(np.mean(scores)) if scores else 100.0
        if not latest_event:
            latest_event = "姿態標準 (專注聽講)"

        return {
            "student_count": num_persons,
            "attention_score": round(avg_score, 1),
            "latest_event": latest_event,
            "events": events,
            "annotated_frame": out_frame
        }
