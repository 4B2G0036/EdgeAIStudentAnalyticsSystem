"""
core/drawing.py
===============
High-performance, Unicode/CJK-aware visual overlay and text drawing module.

Addresses OpenCV's cv2.putText limitation (ASCII-only Hershey fonts) by using
cached TrueType fonts (e.g., Microsoft JhengHei on Windows, Noto Sans CJK on Linux)
with Pillow for crisp, anti-aliased Chinese and English text rendering.

Includes automatic ASCII fallback mapping so that even in stripped headless
environments lacking CJK fonts, text never renders as question marks ('????').
"""
from __future__ import annotations

import logging
import os
import platform
from functools import lru_cache
from typing import Optional, Sequence

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("core.drawing")

# Candidate fonts by OS priority
_WINDOWS_FONTS = [
    r"C:\Windows\Fonts\msjhbd.ttc",   # Microsoft JhengHei Bold
    r"C:\Windows\Fonts\msjh.ttc",     # Microsoft JhengHei
    r"C:\Windows\Fonts\mingliu.ttc",  # MingLiU
    r"C:\Windows\Fonts\simhei.ttf",   # SimHei
    r"C:\Windows\Fonts\arial.ttf",    # Fallback Latin
]

_LINUX_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

_DARWIN_FONTS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]

# Translation table to prevent '????' when no CJK font is available
_ASCII_FALLBACK_MAP = {
    "人數": "Students",
    "專注度": "Attention",
    "分": "pts",
    "趴睡": "SLEEPING",
    "手機": "PHONE",
    "疑似使用手機": "PHONE_SUSPECTED",
    "分心": "DISTRACTED",
    "東張西望": "DISTRACTED",
    "專注": "ATTENTIVE",
    "姿態標準": "ATTENTIVE",
    "未在座位區偵測到學生": "No students in ROI",
    "未偵測到學生": "No students detected",
    "等待影像來源": "Waiting for video source",
    "攝影機串流傳輸中 (等待畫面)...": "Camera stream standby...",
    "攝影機等待畫面中...": "Camera stream standby...",
}


@lru_cache(maxsize=1)
def find_cjk_font_path() -> Optional[str]:
    """Find the best available CJK-capable TrueType/OpenType font on the host system."""
    system = platform.system().lower()
    candidates = []
    if "windows" in system:
        candidates = _WINDOWS_FONTS
    elif "darwin" in system:
        candidates = _DARWIN_FONTS
    else:
        candidates = _LINUX_FONTS

    for path in candidates:
        if os.path.isfile(path):
            logger.info("Found CJK font: %s", path)
            return path

    logger.warning("No system CJK font found; using PIL default font with ASCII fallback.")
    return None


@lru_cache(maxsize=32)
def get_font(size: int = 15, bold: bool = True) -> ImageFont.ImageFont:
    """Return a cached ImageFont instance for the specified size."""
    font_path = find_cjk_font_path()
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception as e:
            logger.warning("Failed to load TrueType font '%s': %e", font_path, e)

    return ImageFont.load_default()


def has_cjk_font() -> bool:
    """Check if a CJK font is loaded."""
    return find_cjk_font_path() is not None


def sanitize_text_for_ascii(text: str) -> str:
    """Safely map Chinese terms to ASCII English representation."""
    out = text
    for zh, en in _ASCII_FALLBACK_MAP.items():
        out = out.replace(zh, en)
    return out


def draw_text_bgr(
    image: np.ndarray,
    text: str,
    org: tuple[int, int],
    font_size: int = 15,
    color_bgr: tuple[int, int, int] = (255, 255, 255),
    bg_color_bgr: Optional[tuple[int, int, int]] = None,
    bold: bool = True,
    padding: tuple[int, int] = (4, 2),
) -> np.ndarray:
    """
    Draw a single anti-aliased text string onto a BGR numpy image in-place.
    
    Parameters
    ----------
    image        : uint8 BGR numpy array
    text         : Text string (supports Unicode/Traditional Chinese)
    org          : (x, y) Top-left coordinate of text
    font_size    : Font size in pixels
    color_bgr    : (B, G, R) text color
    bg_color_bgr : Optional (B, G, R) background pill color
    bold         : Whether to use bold weight
    padding      : (pad_x, pad_y) padding around text if bg_color_bgr is provided
    
    Returns
    -------
    image : Modified image with rendered text
    """
    return draw_labels_bgr(
        image,
        [
            {
                "text": text,
                "org": org,
                "font_size": font_size,
                "color_bgr": color_bgr,
                "bg_color_bgr": bg_color_bgr,
                "bold": bold,
                "padding": padding,
            }
        ],
    )


def draw_labels_bgr(
    image: np.ndarray,
    labels: Sequence[dict],
) -> np.ndarray:
    """
    Batch-draw multiple Unicode/Chinese text labels onto a BGR numpy image.
    Executes a single PIL conversion pass for maximum runtime performance.

    Each label dict should contain:
      - text: str
      - org: (x, y) top-left coordinate
      - font_size: int (default 15)
      - color_bgr: (B, G, R) tuple
      - bg_color_bgr: Optional (B, G, R) background pill color
      - padding: Optional (pad_x, pad_y) tuple (default (4, 2))
      - bold: Optional bool (default True)
    """
    if not labels or image is None or image.size == 0:
        return image

    cjk_available = has_cjk_font()
    pil_img = Image.fromarray(image)
    draw = ImageDraw.Draw(pil_img)

    for item in labels:
        raw_text = str(item.get("text", ""))
        text = raw_text if cjk_available else sanitize_text_for_ascii(raw_text)
        org = item.get("org", (10, 10))
        font_size = int(item.get("font_size", 15))
        bold = bool(item.get("bold", True))
        color_bgr = item.get("color_bgr", (255, 255, 255))
        bg_color_bgr = item.get("bg_color_bgr")
        pad_x, pad_y = item.get("padding", (4, 2))

        font = get_font(size=font_size, bold=bold)

        if bg_color_bgr is not None:
            bbox = draw.textbbox(org, text, font=font)
            rect = (
                max(0, bbox[0] - pad_x),
                max(0, bbox[1] - pad_y),
                min(image.shape[1], bbox[2] + pad_x),
                min(image.shape[0], bbox[3] + pad_y),
            )
            draw.rectangle(rect, fill=bg_color_bgr)

        draw.text(org, text, font=font, fill=color_bgr)

    # In-place write back to avoid memory re-allocation
    np.copyto(image, np.asarray(pil_img))
    return image

