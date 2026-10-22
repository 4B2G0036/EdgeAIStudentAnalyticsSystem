"""
tests/test_core.py
==================
Unit tests for the Edge AI Visual Core (core/).

Covers:
- ROI polygon filtering (core.roi)
- Head pose estimation logic (core.head_pose)
- Abnormal pose deduction & attention scoring (core.pose_analyzer)
- Multi-person tracker & occlusion tolerance (core.tracker)
- Privacy Gaussian blur on head regions (core.privacy)
- Core data models (core.models)
"""
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import cv2

from core.models import PoseFlag, TrackedPerson, FrameResult
from core.roi import is_point_in_roi, filter_persons_by_roi
from core.head_pose import estimate_head_pose
from core.tracker import PersonTracker
from core.privacy import apply_privacy_blur
from core.pose_analyzer import PoseAnalyzer


def test_roi_polygon_filtering():
    """Test point in polygon and person filtering."""
    # Standard square ROI: [0.2, 0.2] to [0.8, 0.8]
    poly = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]

    assert is_point_in_roi((0.5, 0.5), poly) is True
    assert is_point_in_roi((0.1, 0.1), poly) is False
    assert is_point_in_roi((0.9, 0.9), poly) is False

    # None polygon should allow all points
    assert is_point_in_roi((0.1, 0.1), None) is True

    # Test filter_persons_by_roi
    dummy_kpts = np.zeros((17, 3), dtype=np.float32)
    p_inside = TrackedPerson(
        tracking_id=1,
        bbox=(0.4, 0.4, 0.6, 0.6), # Center = (0.5, 0.5)
        keypoints=dummy_kpts,
        confidence=0.9,
    )
    p_outside = TrackedPerson(
        tracking_id=2,
        bbox=(0.02, 0.02, 0.08, 0.08), # Center = (0.05, 0.05)
        keypoints=dummy_kpts,
        confidence=0.9,
    )

    filtered = filter_persons_by_roi([p_inside, p_outside], poly)
    assert len(filtered) == 1
    assert filtered[0].tracking_id == 1
    assert p_inside.in_roi is True
    assert p_outside.in_roi is False


def test_head_pose_strategy1():
    """Test Strategy 1: Nose + Eyes geometry."""
    kpts = np.zeros((17, 3), dtype=np.float32)
    # Nose
    kpts[0] = [320.0, 240.0, 0.9]
    # Left eye
    kpts[1] = [300.0, 220.0, 0.9]
    # Right eye
    kpts[2] = [340.0, 220.0, 0.9]

    yaw, pitch, strategy, is_looking = estimate_head_pose(kpts, tracking_id=1)
    assert strategy == 1
    # Symmetric eyes around nose -> yaw close to 0
    assert abs(yaw) < 5.0
    assert is_looking is True


def test_head_pose_strategy2_ears():
    """Test Strategy 2 fallback: Ears + Shoulders."""
    kpts = np.zeros((17, 3), dtype=np.float32)
    # Eyes & nose low confidence
    kpts[0] = [320.0, 240.0, 0.1]
    kpts[1] = [300.0, 220.0, 0.1]
    kpts[2] = [340.0, 220.0, 0.1]
    # Ears valid
    kpts[3] = [280.0, 230.0, 0.9] # left ear
    kpts[4] = [360.0, 230.0, 0.9] # right ear
    # Shoulders valid
    kpts[5] = [270.0, 300.0, 0.9] # left shoulder
    kpts[6] = [370.0, 300.0, 0.9] # right shoulder

    yaw, pitch, strategy, is_looking = estimate_head_pose(kpts, tracking_id=2)
    assert strategy == 2
    assert abs(yaw) < 10.0


def test_tracker_occlusion_and_drift_protection():
    """Test PersonTracker persistence across frames and occlusion tolerance."""
    tracker = PersonTracker(max_occlusion_frames=30, iou_match_thresh=0.3)

    # Frame 1: Person at box A
    box_a = np.array([[100.0, 100.0, 200.0, 200.0]], dtype=np.float32)
    ids_1 = tracker.update(box_a)
    assert len(ids_1) == 1
    assigned_id = ids_1[0]

    # Frame 2: Person moves slightly
    box_a_moved = np.array([[105.0, 102.0, 205.0, 202.0]], dtype=np.float32)
    ids_2 = tracker.update(box_a_moved)
    assert ids_2[0] == assigned_id

    # Frame 3-5: Person disappears (occluded)
    empty_boxes = np.zeros((0, 4), dtype=np.float32)
    for _ in range(3):
        tracker.update(empty_boxes)

    # Frame 6: Person reappears at almost same location within 30 frames
    box_a_reappear = np.array([[104.0, 101.0, 204.0, 201.0]], dtype=np.float32)
    ids_6 = tracker.update(box_a_reappear)
    assert ids_6[0] == assigned_id, "Track ID must be preserved during brief occlusion!"


def test_privacy_blur_leaves_non_head_regions():
    """Test Gaussian blur is applied to head regions while non-head regions remain identical."""
    # Create test pattern frame: solid white
    frame = np.ones((400, 400, 3), dtype=np.uint8) * 200
    # Add high frequency noise in head area (100, 100) to (160, 160)
    frame[100:160, 100:160] = np.random.randint(0, 255, (60, 60, 3), dtype=np.uint8)

    boxes = np.array([[100.0, 100.0, 200.0, 300.0]], dtype=np.float32)
    kpts = np.zeros((1, 17, 3), dtype=np.float32)
    # Head keypoints
    kpts[0, 0] = [130.0, 130.0, 0.9] # nose
    kpts[0, 1] = [120.0, 120.0, 0.9] # eye
    kpts[0, 2] = [140.0, 120.0, 0.9] # eye

    blurred = apply_privacy_blur(frame, boxes, kpts)

    # Frame outside head region should remain untouched
    assert np.array_equal(frame[320:390, 320:390], blurred[320:390, 320:390])
    # Frame inside head region should differ due to blur
    assert not np.array_equal(frame[100:160, 100:160], blurred[100:160, 100:160])


def test_pose_analyzer_scoring():
    """Test scoring logic for various posture conditions."""
    analyzer = PoseAnalyzer.get_instance()

    # Upright looking at board: 50 + 50 = 100
    score_normal = analyzer._calculate_score(is_looking=True, flags=set())
    assert score_normal == 100.0

    # Looking away (distracted): 0 + 50 = 50
    score_distracted = analyzer._calculate_score(is_looking=False, flags={PoseFlag.DISTRACTED})
    assert score_distracted == 50.0

    # Sleeping: looking=False, upright=False, penalty=-30 -> clamped to 0
    score_sleeping = analyzer._calculate_score(is_looking=False, flags={PoseFlag.SLEEPING})
    assert score_sleeping == 0.0

    # Phone suspected: looking=False, upright=True, penalty=-50 -> 50 - 50 = 0
    score_phone = analyzer._calculate_score(is_looking=False, flags={PoseFlag.PHONE_SUSPECTED})
    assert score_phone == 0.0


def test_frame_result_structure():
    """Test FrameResult properties and event generation."""
    p1 = TrackedPerson(
        tracking_id=1,
        bbox=(0.1, 0.1, 0.3, 0.4),
        keypoints=np.zeros((17, 3), dtype=np.float32),
        confidence=0.88,
        in_roi=True,
        pose_flags={PoseFlag.PHONE_SUSPECTED},
        attention_score=0.0,
    )
    p2 = TrackedPerson(
        tracking_id=2,
        bbox=(0.5, 0.1, 0.7, 0.4),
        keypoints=np.zeros((17, 3), dtype=np.float32),
        confidence=0.92,
        in_roi=True,
        pose_flags=set(),
        attention_score=100.0,
    )

    result = FrameResult(
        frame_id="test-001",
        tracked_persons=[p1, p2],
        avg_attention_score=50.0,
        active_flags={PoseFlag.PHONE_SUSPECTED},
        latest_event_desc="S001: 疑似使用手機",
        inference_ms=15.2,
        annotated_frame=None,
    )

    assert result.student_count == 2
    assert len(result.events) == 1
    assert "ID001" in result.events[0]
    assert "PHONE_SUSPECTED" in result.events[0]


if __name__ == "__main__":
    print("Running Edge AI Visual Core tests...")
    test_roi_polygon_filtering()
    print("  ✓ test_roi_polygon_filtering passed")
    test_head_pose_strategy1()
    print("  ✓ test_head_pose_strategy1 passed")
    test_head_pose_strategy2_ears()
    print("  ✓ test_head_pose_strategy2_ears passed")
    test_tracker_occlusion_and_drift_protection()
    print("  ✓ test_tracker_occlusion_and_drift_protection passed")
    test_privacy_blur_leaves_non_head_regions()
    print("  ✓ test_privacy_blur_leaves_non_head_regions passed")
    test_pose_analyzer_scoring()
    print("  ✓ test_pose_analyzer_scoring passed")
    test_frame_result_structure()
    print("  ✓ test_frame_result_structure passed")
    print("\n🎉 ALL TESTS PASSED!")

