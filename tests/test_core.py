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


def test_inference_engine_execution():
    """Test InferenceEngine vectorised pipeline loads and produces valid output types."""
    from core.inference import InferenceEngine
    engine = InferenceEngine.get_instance()
    dummy = np.zeros((480, 640, 3), dtype=np.uint8)
    boxes, kpts, scores, trace_id = engine.infer(dummy)
    assert isinstance(boxes, np.ndarray)
    assert isinstance(kpts, np.ndarray)
    assert isinstance(scores, np.ndarray)
    assert isinstance(trace_id, str)
    assert len(boxes.shape) == 2 and boxes.shape[1] == 4
    assert len(kpts.shape) == 3 and kpts.shape[1:] == (17, 3)


def test_stream_broadcaster_and_worker_offload():
    """Test StreamBroadcaster multi-consumer pub-sub and webcam worker thread offloading."""
    import cv2
    from api.routers.stream import StreamBroadcaster
    from api.routers.realtime import _process_webcam_frame_sync

    # 1. Broadcaster pub-sub tests
    broadcaster = StreamBroadcaster()
    assert broadcaster.viewer_count == 0
    assert not broadcaster._has_subscribers.is_set()

    q1 = broadcaster.subscribe()
    q2 = broadcaster.subscribe()
    assert broadcaster.viewer_count == 2
    assert broadcaster._has_subscribers.is_set()

    # Broadcast frame
    dummy_frame = b"fake_jpeg_bytes_123"
    broadcaster._broadcast_frame(dummy_frame)
    assert q1.get_nowait() == dummy_frame
    assert q2.get_nowait() == dummy_frame

    # Unsubscribe
    broadcaster.unsubscribe(q1)
    assert broadcaster.viewer_count == 1
    broadcaster.unsubscribe(q2)
    assert broadcaster.viewer_count == 0
    assert not broadcaster._has_subscribers.is_set()

    # 2. Webcam worker thread worker function
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    ret, jpeg = cv2.imencode('.jpg', dummy_img)
    assert ret
    res, err = _process_webcam_frame_sync(jpeg.tobytes())
    assert err is None
    assert res["status"] == "ok"
    assert "student_count" in res
    assert "attention_score" in res


def test_phase2_reports_and_realtime_streams():
    """Test Phase 2 unified report generation and SSE/WebSocket realtime payload structure."""
    import asyncio
    from api.routers.reports import _render_pdf_report, _render_text_report
    from api.routers.realtime import get_current_realtime_payload
    
    dummy_summary = {
        "class_name": "測試課程",
        "teacher": "林教授",
        "started_at": "2026-11-04T00:00:00",
        "ended_at": "2026-11-04T01:00:00",
        "max_student_count": 25,
        "avg_attention_score": 88.5,
        "total_abnormal_events": 2
    }
    
    # 1. Verify text report generator
    txt_bytes = _render_text_report("test-sess-001", dummy_summary, "2026-11-04T00:00:00", "2026-11-04T01:00:00")
    assert isinstance(txt_bytes, bytes)
    assert "測試課程" in txt_bytes.decode("utf-8")
    assert "88.5%" in txt_bytes.decode("utf-8")
    
    # 2. Verify PDF report generator
    pdf_bytes = _render_pdf_report("test-sess-001", dummy_summary, "2026-11-04T00:00:00", "2026-11-04T01:00:00")
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")
    
    # 3. Verify realtime telemetry payload generator
    payload = asyncio.run(get_current_realtime_payload())
    assert isinstance(payload, dict)
    assert "attention_score" in payload
    assert "active_student_count" in payload
    assert "latest_event" in payload
    assert "timestamp" in payload


def test_phase3_metric_batch_writer():
    """Test Phase 3 MetricBatchWriter buffering, queue draining and graceful flush."""
    from database.writer import MetricBatchWriter
    writer = MetricBatchWriter(batch_size=10, flush_interval_s=10.0)
    assert writer._queue.empty()
    
    # Queue multiple metrics
    writer.write_metric("test-batch-001", 90.0, 5)
    writer.write_metric("test-batch-001", 92.5, 5)
    assert writer._queue.qsize() == 2
    
    # Flush drains queue
    flushed = writer.flush()
    assert writer._queue.empty()
    assert flushed >= 0
    writer.stop()


def _make_upper_body_kpts(nose_y: float, left_sh_y: float = 300.0, right_sh_y: float = 300.0) -> np.ndarray:
    """Build a synthetic upper-body skeleton (shoulders y≈300, bbox 200..440 x 100..500)."""
    kpts = np.zeros((17, 3), dtype=np.float32)
    kpts[0] = [320.0, nose_y, 0.9]        # nose
    kpts[1] = [305.0, nose_y - 20, 0.9]   # left eye
    kpts[2] = [335.0, nose_y - 20, 0.9]   # right eye
    kpts[5] = [260.0, left_sh_y, 0.9]     # left shoulder
    kpts[6] = [380.0, right_sh_y, 0.9]    # right shoulder
    return kpts


def test_sleeping_not_triggered_by_slight_head_motion():
    """輕微低頭 / 俯仰角中等 / 單幀抖動不可被誤判為趴睡 (回歸測試)。"""
    analyzer = PoseAnalyzer.get_instance()
    bbox = np.array([200.0, 100.0, 440.0, 500.0], dtype=np.float32)  # bbox_h = 400

    # 1) 輕微低頭：鼻子距肩線 55px (13.8% bbox_h)。舊門檻 0.20 會誤判，新門檻 0.12 不會
    kpts = _make_upper_body_kpts(nose_y=245.0)
    for _ in range(analyzer.sleeping_confirm_frames + 3):
        flags = analyzer._detect_abnormal_pose(kpts, bbox, 0.0, 0.0, tracking_id=9101)
        assert PoseFlag.SLEEPING not in flags

    # 2) 俯仰角 -50° (舊門檻 -45° 會誤判)，但肩線水平、鼻子離肩線很遠 -> 不是趴睡
    kpts = _make_upper_body_kpts(nose_y=190.0)
    for _ in range(analyzer.sleeping_confirm_frames + 3):
        flags = analyzer._detect_abnormal_pose(kpts, bbox, 0.0, -50.0, tracking_id=9102)
        assert PoseFlag.SLEEPING not in flags

    # 3) 單純肩線歪斜 (舊版 0.30 即誤判)：肩高差 130px (32% bbox_h) 但頭部仍高於肩線
    kpts = _make_upper_body_kpts(nose_y=190.0, left_sh_y=240.0, right_sh_y=370.0)
    for _ in range(analyzer.sleeping_confirm_frames + 3):
        flags = analyzer._detect_abnormal_pose(kpts, bbox, 0.0, 0.0, tracking_id=9103)
        assert PoseFlag.SLEEPING not in flags


def test_sleeping_requires_sustained_head_down_and_releases():
    """真正趴下需連續多幀才確認；短暫動作不觸發；起身後需連續多幀才解除。"""
    analyzer = PoseAnalyzer.get_instance()
    bbox = np.array([200.0, 100.0, 440.0, 500.0], dtype=np.float32)
    down = _make_upper_body_kpts(nose_y=292.0)   # 鼻子幾乎貼在肩線 (差 8px)
    up = _make_upper_body_kpts(nose_y=190.0)

    # 短暫低頭 (少於確認幀數) 後恢復 -> 不觸發
    tid = 9201
    for _ in range(analyzer.sleeping_confirm_frames - 1):
        flags = analyzer._detect_abnormal_pose(down, bbox, 0.0, 0.0, tracking_id=tid)
        assert PoseFlag.SLEEPING not in flags
    flags = analyzer._detect_abnormal_pose(up, bbox, 0.0, 0.0, tracking_id=tid)
    assert PoseFlag.SLEEPING not in flags

    # 持續趴下 -> 於第 N 幀確認
    tid = 9202
    results = [
        PoseFlag.SLEEPING in analyzer._detect_abnormal_pose(down, bbox, 0.0, 0.0, tracking_id=tid)
        for _ in range(analyzer.sleeping_confirm_frames)
    ]
    assert results[:-1] == [False] * (analyzer.sleeping_confirm_frames - 1)
    assert results[-1] is True

    # 起身：連續 RELEASE 幀才解除 (中途仍維持趴睡，防閃爍)
    for i in range(analyzer.sleeping_release_frames):
        flags = analyzer._detect_abnormal_pose(up, bbox, 0.0, 0.0, tracking_id=tid)
        expected = i < analyzer.sleeping_release_frames - 1
        assert (PoseFlag.SLEEPING in flags) is expected

    # 未提供 tracking_id 時不做時間濾波 (直接回傳單幀結果)
    flags = analyzer._detect_abnormal_pose(down, bbox, 0.0, 0.0)
    assert PoseFlag.SLEEPING in flags


def test_head_pose_pitch_stable_when_turning_head():
    """轉頭導致雙眼距離縮小時，俯仰角不可被放大成極端值。"""
    kpts = np.zeros((17, 3), dtype=np.float32)
    kpts[0] = [322.0, 232.0, 0.9]   # nose
    kpts[1] = [315.0, 220.0, 0.9]   # left eye  (eye_dist = 10, 側臉)
    kpts[2] = [325.0, 220.0, 0.9]   # right eye
    kpts[5] = [260.0, 300.0, 0.9]   # shoulders (width 120)
    kpts[6] = [380.0, 300.0, 0.9]
    yaw, pitch, strategy, _ = estimate_head_pose(kpts, tracking_id=3)
    assert strategy == 1
    # 舊算法: (220-232)/10*60+20 = -52° (會被判趴睡)；新算法以肩寬穩定尺度，應遠小於此
    assert pitch > -30.0
    assert -90.0 <= pitch <= 90.0 and -90.0 <= yaw <= 90.0


def test_cjk_unicode_drawing_and_action_labels():
    """Verify that Chinese posture labels and stats banners render without '????' artifacts."""
    from core.drawing import draw_text_bgr, draw_labels_bgr, sanitize_text_for_ascii
    
    # 1. Verify ASCII sanitizer
    sanitized = sanitize_text_for_ascii("人數: 1 | 專注度: 50分 [趴睡]")
    assert "Students" in sanitized
    assert "Attention" in sanitized
    assert "SLEEPING" in sanitized
    assert "人" not in sanitized
    
    # 2. Verify drawing onto frame
    img = np.zeros((200, 400, 3), dtype=np.uint8)
    draw_text_bgr(img, "[AI CORE LIVE] 人數: 2 | 專注度: 80分", (10, 10), font_size=14)
    assert img.max() > 0
    
    # 3. Verify batch drawing with posture tags
    items = [
        {"text": "S001 | 100分 [專注]", "org": (10, 50), "color_bgr": (0, 230, 115), "bg_color_bgr": (20, 24, 33)},
        {"text": "S002 | 50分 [分心]", "org": (10, 90), "color_bgr": (0, 204, 255), "bg_color_bgr": (20, 24, 33)},
        {"text": "S003 | 20分 [趴睡]", "org": (10, 130), "color_bgr": (60, 60, 255), "bg_color_bgr": (20, 24, 33)},
    ]
    draw_labels_bgr(img, items)
    assert img.max() > 0


def test_tracker_drift_revival_and_empty_aging():
    """Verify PersonTracker ID-drift revival, empty frame aging, and greedy row/col cleanup."""
    tracker = PersonTracker(max_occlusion_frames=5, iou_match_thresh=0.3, iou_inherit_thresh=0.7)
    
    # 1. First frame: person at box A
    box_a = np.array([[100.0, 100.0, 200.0, 200.0]], dtype=np.float32)
    ids_1 = tracker.update(box_a)
    assert ids_1 == [1]

    # 2. Feed empty frames past max_occlusion_frames to age it into lost_tracks
    empty = np.zeros((0, 4), dtype=np.float32)
    for _ in range(6):
        tracker.update(empty)
    assert len(tracker._tracks) == 0
    assert len(tracker._lost_tracks) == 1
    assert tracker._lost_tracks[0].tracking_id == 1

    # 3. Person returns at nearly identical box: should revive with ID 1
    ids_revived = tracker.update(box_a)
    assert ids_revived == [1]
    assert len(tracker._tracks) == 1
    assert len(tracker._lost_tracks) == 0


def test_metric_batch_writer_requeue():
    """Verify MetricBatchWriter requeues failed batch with memory bounds protection."""
    from database.writer import MetricBatchWriter
    writer = MetricBatchWriter(batch_size=5, flush_interval_s=10.0, max_pending=10)
    
    # Simulate a failed batch
    failed_batch = [
        {"timestamp": 1, "metadata": {"session_id": "s1"}, "attention_score": 90.0, "student_count": 1},
        {"timestamp": 2, "metadata": {"session_id": "s1"}, "attention_score": 85.0, "student_count": 1},
    ]
    writer._requeue(failed_batch)
    assert writer._queue.qsize() == 2

    # Overflow protection check: filling past max_pending drops new docs to prevent OOM
    huge_batch = [{"dummy": i} for i in range(15)]
    writer._requeue(huge_batch)
    assert writer._queue.qsize() == 2  # Remains capped, huge_batch dropped
    writer.stop()


def test_frame_result_persister_lifecycle():
    """Verify FrameResultPersister parsing, event tracking, and grace frames closing."""
    from api.persistence import FrameResultPersister, parse_event
    
    student, event_type = parse_event("ID001: 趴睡 (SLEEPING)")
    assert student == "ID001"
    assert event_type == "趴睡 (SLEEPING)"

    persister = FrameResultPersister(session_ttl_s=100.0, close_grace_frames=2)
    # Mock resolved session id
    persister._session_id = "test-session-mock"
    persister._session_checked_at = 9999999999.0

    # 1. Event appears
    persister.persist(80.0, 1, ["ID001: 趴睡 (SLEEPING)"])
    assert ("ID001", "趴睡 (SLEEPING)") in persister._active

    # 2. Event disappears in next frame (miss count = 1, below grace=2, still active)
    persister.persist(100.0, 1, [])
    assert ("ID001", "趴睡 (SLEEPING)") in persister._active
    assert persister._active[("ID001", "趴睡 (SLEEPING)")]["miss"] == 1

    # 3. Disappears second time (miss count = 2 >= grace=2, closed and purged)
    persister.persist(100.0, 1, [])
    assert ("ID001", "趴睡 (SLEEPING)") not in persister._active


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
    test_inference_engine_execution()
    print("  ✓ test_inference_engine_execution passed")
    test_stream_broadcaster_and_worker_offload()
    print("  ✓ test_stream_broadcaster_and_worker_offload passed")
    test_phase2_reports_and_realtime_streams()
    print("  ✓ test_phase2_reports_and_realtime_streams passed")
    test_phase3_metric_batch_writer()
    print("  ✓ test_phase3_metric_batch_writer passed")
    test_cjk_unicode_drawing_and_action_labels()
    print("  ✓ test_cjk_unicode_drawing_and_action_labels passed")
    test_sleeping_not_triggered_by_slight_head_motion()
    print("  ✓ test_sleeping_not_triggered_by_slight_head_motion passed")
    test_sleeping_requires_sustained_head_down_and_releases()
    print("  ✓ test_sleeping_requires_sustained_head_down_and_releases passed")
    test_head_pose_pitch_stable_when_turning_head()
    print("  ✓ test_head_pose_pitch_stable_when_turning_head passed")
    test_tracker_drift_revival_and_empty_aging()
    print("  ✓ test_tracker_drift_revival_and_empty_aging passed")
    test_metric_batch_writer_requeue()
    print("  ✓ test_metric_batch_writer_requeue passed")
    test_frame_result_persister_lifecycle()
    print("  ✓ test_frame_result_persister_lifecycle passed")
    print("\n🎉 ALL TESTS PASSED!")

