"""
core/models.py
==============
Core data structures for the Edge AI Student Analytics System.

Defines:
- PoseFlag      : Enum of detectable abnormal pose states
- TrackedPerson : Per-frame snapshot of a tracked individual
- FrameResult   : Complete result of one inference pass
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import numpy as np


class PoseFlag(Enum):
    """Detectable abnormal posture states produced by the pose analyzer."""
    SLEEPING        = auto()   # 趴睡 – head near desk
    PHONE_SUSPECTED = auto()   # 疑似使用手機 – wrist low + head bowed
    DISTRACTED      = auto()   # 東張西望 – large yaw deviation


@dataclass
class TrackedPerson:
    """
    Snapshot of a single tracked person in one video frame.

    Fields
    ------
    tracking_id   : Stable integer ID maintained by the tracker across frames.
    bbox          : Bounding-box in normalised coordinates (x1,y1,x2,y2) in [0,1].
    keypoints     : Shape (17, 3) array – (x_px, y_px, conf) per COCO keypoint.
    confidence    : YOLO detection confidence score [0, 1].
    in_roi        : Whether the person's bbox centre falls inside the defined ROI.
    pose_flags    : Set of currently active PoseFlag values.
    attention_score : Computed per-frame attention score [0, 100].
    head_yaw      : Estimated yaw angle in degrees (left/right rotation).
    head_pitch    : Estimated pitch angle in degrees (up/down tilt).
    last_seen_at  : Unix timestamp of the frame this snapshot was captured.
    """
    tracking_id     : int
    bbox            : tuple[float, float, float, float]   # normalised (x1,y1,x2,y2)
    keypoints       : np.ndarray                           # (17, 3) float32
    confidence      : float
    in_roi          : bool = True
    pose_flags      : set[PoseFlag] = field(default_factory=set)
    attention_score : float = 100.0
    head_yaw        : float = 0.0
    head_pitch      : float = 0.0
    last_seen_at    : float = field(default_factory=time.time)


@dataclass
class FrameResult:
    """
    Aggregated output from a single full inference pass on one camera frame.

    Fields
    ------
    frame_id          : Unique trace identifier for this frame (UUID or timestamp).
    tracked_persons   : List of TrackedPerson snapshots, one per detected individual.
    avg_attention_score : Class-wide average attention score [0, 100].
    active_flags      : Union of all pose flags currently raised across all persons.
    latest_event_desc : Human-readable description of the most recent abnormal event.
    inference_ms      : Time taken for the YOLO forward pass in milliseconds.
    annotated_frame   : OpenCV BGR image with overlays drawn (privacy-filtered).
    timestamp         : Unix timestamp when this frame was processed.
    """
    frame_id            : str
    tracked_persons     : list[TrackedPerson]
    avg_attention_score : float
    active_flags        : set[PoseFlag]
    latest_event_desc   : str
    inference_ms        : float
    annotated_frame     : Optional[np.ndarray]
    timestamp           : float = field(default_factory=time.time)

    @property
    def student_count(self) -> int:
        """Number of persons detected in this frame."""
        return len(self.tracked_persons)

    @property
    def events(self) -> list[str]:
        """List of event strings for all persons with active flags."""
        out = []
        for p in self.tracked_persons:
            for flag in p.pose_flags:
                label = {
                    PoseFlag.SLEEPING:        "趴睡 (SLEEPING)",
                    PoseFlag.PHONE_SUSPECTED: "疑似使用手機 (PHONE_SUSPECTED)",
                    PoseFlag.DISTRACTED:      "東張西望 (DISTRACTED)",
                }.get(flag, flag.name)
                out.append(f"ID{p.tracking_id:03d}: {label}")
        return out
