"""
core/tracker.py
===============
Lightweight multi-person tracker using IoU-based greedy matching.

Features
--------
- Assigns stable ``tracking_id`` integers across frames.
- Tolerates up to ``max_occlusion_frames`` (default 30 ≈ 6 s @ 5 FPS) of 
  disappearance before terminating a track.
- ID Drift Protection: when a brand-new detection overlaps a *just-lost* track
  with IoU > ``iou_inherit_thresh`` (default 0.80), the old ID is inherited
  instead of creating a new one, preventing FSM state resets on brief occlusions.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger("core.tracker")

_IOU_INHERIT_THRESH = 0.80   # IoU threshold for ID re-use (ID drift protection)
_MAX_OCCLUSION_FRAMES = 30   # frames before track is permanently terminated


@dataclass
class _Track:
    """Internal state for a single tracked person."""
    tracking_id     : int
    bbox            : np.ndarray          # (4,) float32  xyxy pixel coords
    last_seen_frame : int                 # frame index of last matched detection
    is_active       : bool = True
    created_at      : float = field(default_factory=time.time)


def _iou_matrix(boxes_a: np.ndarray, boxes_b: np.ndarray) -> np.ndarray:
    """
    Compute pairwise IoU between two sets of bounding boxes.

    Parameters
    ----------
    boxes_a : (M, 4) float32  xyxy
    boxes_b : (N, 4) float32  xyxy

    Returns
    -------
    iou_mat : (M, N) float32
    """
    M, N = len(boxes_a), len(boxes_b)
    if M == 0 or N == 0:
        return np.zeros((M, N), dtype=np.float32)

    # Broadcast
    a = boxes_a[:, np.newaxis, :]   # (M, 1, 4)
    b = boxes_b[np.newaxis, :, :]   # (1, N, 4)

    xi1 = np.maximum(a[..., 0], b[..., 0])
    yi1 = np.maximum(a[..., 1], b[..., 1])
    xi2 = np.minimum(a[..., 2], b[..., 2])
    yi2 = np.minimum(a[..., 3], b[..., 3])
    inter = np.maximum(0.0, xi2 - xi1) * np.maximum(0.0, yi2 - yi1)

    area_a = (boxes_a[:, 2] - boxes_a[:, 0]) * (boxes_a[:, 3] - boxes_a[:, 1])  # (M,)
    area_b = (boxes_b[:, 2] - boxes_b[:, 0]) * (boxes_b[:, 3] - boxes_b[:, 1])  # (N,)
    union  = area_a[:, np.newaxis] + area_b[np.newaxis, :] - inter               # (M,N)

    return inter / (union + 1e-9)


class PersonTracker:
    """
    Greedy IoU-based multi-object tracker for classroom students.

    Maintains a list of active tracks and a short-lived list of recently lost
    tracks for ID-drift protection.

    Usage
    -----
    tracker = PersonTracker()
    tracking_ids = tracker.update(detected_boxes_xyxy, frame_index)
    """

    def __init__(
        self,
        max_occlusion_frames: int = _MAX_OCCLUSION_FRAMES,
        iou_match_thresh: float = 0.35,
        iou_inherit_thresh: float = _IOU_INHERIT_THRESH,
    ) -> None:
        self._tracks        : list[_Track] = []
        self._lost_tracks   : list[_Track] = []   # tracks that just disappeared
        self._next_id       : int  = 1
        self._max_occl      : int  = max_occlusion_frames
        self._iou_match     : float = iou_match_thresh
        self._iou_inherit   : float = iou_inherit_thresh
        self._frame_idx     : int  = 0

    # ── Public API ─────────────────────────────────────────────────────────────
    def update(
        self,
        detected_boxes: np.ndarray,  # (N, 4) float32  xyxy
    ) -> list[int]:
        """
        Match new detections to existing tracks and return a tracking_id for
        every detection in the same order as ``detected_boxes``.

        Parameters
        ----------
        detected_boxes : (N, 4) float32  xyxy pixel coordinates

        Returns
        -------
        tracking_ids : list[int]  length N  – stable integer ID per detection
        """
        self._frame_idx += 1
        N = len(detected_boxes)

        if N == 0:
            self._expire_lost_tracks()
            return []

        # -- Step 1: Match detections against active tracks --------------------
        active   = [t for t in self._tracks if t.is_active]
        assigned = [-1] * N           # detection → track_id  (−1 = unmatched)

        if active:
            track_boxes = np.stack([t.bbox for t in active], axis=0)  # (M, 4)
            iou_mat     = _iou_matrix(track_boxes, detected_boxes)    # (M, N)

            matched_tracks = set()
            matched_dets   = set()

            # Greedy: match highest-IoU pairs first
            for _ in range(min(len(active), N)):
                mi, di = np.unravel_index(np.argmax(iou_mat), iou_mat.shape)
                if iou_mat[mi, di] < self._iou_match:
                    break
                if mi in matched_tracks or di in matched_dets:
                    iou_mat[mi, di] = 0.0
                    continue
                matched_tracks.add(mi)
                matched_dets.add(di)
                assigned[di] = active[mi].tracking_id
                active[mi].bbox = detected_boxes[di].copy()
                active[mi].last_seen_frame = self._frame_idx
                iou_mat[mi, di] = 0.0

        # -- Step 2: ID-Drift Protection for unmatched detections --------------
        #    If a brand-new detection overlaps a *recently-lost* track with
        #    IoU > _iou_inherit_thresh, recycle that track's ID.
        unmatched_dets = [i for i in range(N) if assigned[i] == -1]

        if unmatched_dets and self._lost_tracks:
            lost_boxes = np.stack([t.bbox for t in self._lost_tracks], axis=0)
            new_boxes  = detected_boxes[unmatched_dets]
            iou_mat2   = _iou_matrix(lost_boxes, new_boxes)  # (L, U)

            matched_lost = set()
            for u_idx, det_idx in enumerate(unmatched_dets):
                if u_idx >= iou_mat2.shape[1]:
                    break
                col   = iou_mat2[:, u_idx]
                best  = int(np.argmax(col))
                if col[best] >= self._iou_inherit_thresh and best not in matched_lost:
                    # Revive lost track with inherited ID
                    revived = self._lost_tracks[best]
                    revived.bbox            = detected_boxes[det_idx].copy()
                    revived.last_seen_frame = self._frame_idx
                    revived.is_active       = True
                    self._tracks.append(revived)
                    self._lost_tracks.pop(best)
                    assigned[det_idx] = revived.tracking_id
                    matched_lost.add(best)
                    logger.debug(
                        "ID-Drift Protection: revived ID=%d with IoU=%.2f",
                        revived.tracking_id, col[best],
                    )

        # -- Step 3: Allocate fresh IDs for still-unmatched detections ---------
        for i in range(N):
            if assigned[i] == -1:
                new_track = _Track(
                    tracking_id     = self._next_id,
                    bbox            = detected_boxes[i].copy(),
                    last_seen_frame = self._frame_idx,
                )
                self._tracks.append(new_track)
                assigned[i] = self._next_id
                self._next_id += 1

        # -- Step 4: Mark tracks missing this frame ----------------------------
        active_ids = set(assigned)
        for t in self._tracks:
            if t.tracking_id not in active_ids and t.is_active:
                frames_gone = self._frame_idx - t.last_seen_frame
                if frames_gone >= self._max_occl:
                    t.is_active = False
                    self._lost_tracks.append(t)
                    logger.debug("Track ID=%d TERMINATED after %d missing frames.",
                                 t.tracking_id, frames_gone)

        # Remove terminated tracks from active list
        self._tracks = [t for t in self._tracks if t.is_active]

        self._expire_lost_tracks()
        return assigned

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _expire_lost_tracks(self) -> None:
        """
        Permanently discard lost tracks that have been gone for more than
        double the occlusion window (they can no longer revive).
        """
        cutoff = self._frame_idx - self._max_occl * 2
        self._lost_tracks = [
            t for t in self._lost_tracks
            if t.last_seen_frame > cutoff
        ]

    def reset(self) -> None:
        """Clear all track state (e.g. between sessions)."""
        self._tracks      = []
        self._lost_tracks = []
        self._next_id     = 1
        self._frame_idx   = 0
        logger.info("PersonTracker reset.")
