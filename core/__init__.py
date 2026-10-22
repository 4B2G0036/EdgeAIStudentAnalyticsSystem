"""
core
====
Edge AI Visual Analytics Core Package.

Provides:
- CameraManager, CameraConnectionError (core.camera)
- InferenceEngine (core.inference)
- PersonTracker (core.tracker)
- PoseAnalyzer (core.pose_analyzer)
- TrackedPerson, PoseFlag, FrameResult (core.models)
- apply_privacy_blur (core.privacy)
- estimate_head_pose (core.head_pose)
- is_point_in_roi, filter_persons_by_roi (core.roi)
"""
from core.camera import CameraConnectionError, CameraManager
from core.head_pose import estimate_head_pose
from core.inference import InferenceEngine
from core.models import FrameResult, PoseFlag, TrackedPerson
from core.pose_analyzer import PoseAnalyzer
from core.privacy import apply_privacy_blur
from core.roi import filter_persons_by_roi, is_point_in_roi
from core.tracker import PersonTracker

__all__ = [
    "CameraManager",
    "CameraConnectionError",
    "InferenceEngine",
    "PersonTracker",
    "PoseAnalyzer",
    "TrackedPerson",
    "PoseFlag",
    "FrameResult",
    "apply_privacy_blur",
    "estimate_head_pose",
    "is_point_in_roi",
    "filter_persons_by_roi",
]
