"""
core/roi.py
===========
Region of Interest (ROI) polygon filtering for the classroom vision core.

Purpose
-------
Filters out individuals (such as roaming teachers or pedestrians outside windows)
whose bounding-box centre falls outside a user-defined normalized polygon ROI.

Format
------
ROI polygon is a sequence of normalized vertices:
    [[x0, y0], [x1, y1], [x2, y2], ...]
where coordinates are in the range [0.0, 1.0].
An empty list or None signifies that the entire field of view is valid.
"""
from __future__ import annotations

import logging
from typing import Sequence, Optional, Union

import cv2
import numpy as np

from core.models import TrackedPerson

logger = logging.getLogger("core.roi")

PolygonType = Union[Sequence[Sequence[float]], np.ndarray]


def is_point_in_roi(
    point: tuple[float, float],
    roi_polygon: Optional[PolygonType] = None,
) -> bool:
    """
    Check if a normalized (cx, cy) point lies within the specified ROI polygon.

    Parameters
    ----------
    point       : tuple (cx, cy) in normalized [0.0, 1.0] coordinates.
    roi_polygon : List of [x, y] coordinates, or None.

    Returns
    -------
    bool : True if point is inside or on the boundary of the ROI polygon,
           or if roi_polygon is None / contains fewer than 3 vertices.
    """
    if roi_polygon is None:
        return True

    poly_arr = np.asarray(roi_polygon, dtype=np.float32)
    if len(poly_arr) < 3:
        # Fewer than 3 points cannot form a valid polygon
        return True

    # Ensure shape (N, 1, 2) or (N, 2) for cv2.pointPolygonTest
    if poly_arr.ndim == 2:
        poly_arr = poly_arr.reshape((-1, 1, 2))

    cx, cy = float(point[0]), float(point[1])
    # cv2.pointPolygonTest returns:
    #   positive value if inside
    #   zero if on the edge
    #   negative value if outside
    dist = cv2.pointPolygonTest(poly_arr, (cx, cy), measureDist=False)
    return dist >= 0


def filter_persons_by_roi(
    persons: list[TrackedPerson],
    roi_polygon: Optional[PolygonType] = None,
) -> list[TrackedPerson]:
    """
    Evaluate in_roi for each TrackedPerson and return only those inside the ROI.

    Parameters
    ----------
    persons     : List of TrackedPerson objects (bbox in normalized [0, 1]).
    roi_polygon : List of normalized [x, y] vertices or None.

    Returns
    -------
    list[TrackedPerson] : Filtered list of persons where in_roi is True.
                          Note: each person's `in_roi` attribute is also updated in-place.
    """
    if not persons:
        return []

    if roi_polygon is None or len(roi_polygon) < 3:
        for p in persons:
            p.in_roi = True
        return persons

    filtered = []
    for p in persons:
        # p.bbox is (x1, y1, x2, y2) normalized [0, 1]
        x1, y1, x2, y2 = p.bbox
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        inside = is_point_in_roi((cx, cy), roi_polygon)
        p.in_roi = inside

        if inside:
            filtered.append(p)
        else:
            logger.debug(
                "Person ID=%d at (%.2f, %.2f) filtered out by ROI",
                p.tracking_id, cx, cy
            )

    return filtered
