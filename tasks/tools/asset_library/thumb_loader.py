"""Background thumbnail loader with disk cache."""

import hashlib
import os

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from module.logger import log
from tasks.tools.asset_library.model import ASSET_IMAGES_ROOT

ASSETS_ROOT = os.path.abspath(ASSET_IMAGES_ROOT)
THUMB_CACHE_DIR = os.path.join("data", "asset_library", "thumbnails")
THUMB_SIZE = 120


def _thumb_cache_path(rel_path: str) -> str:
    h = hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:16]
    return os.path.join(THUMB_CACHE_DIR, f"{h}.png")


def _load_cached(rel_path: str) -> QImage | None:
    cache_path = _thumb_cache_path(rel_path)
    if os.path.exists(cache_path):
        img = QImage(cache_path)
        if not img.isNull():
            return img
    return None


def _save_cache(rel_path: str, image: QImage) -> None:
    os.makedirs(THUMB_CACHE_DIR, exist_ok=True)
    cache_path = _thumb_cache_path(rel_path)
    image.save(cache_path, "PNG")


def _cv2_to_qimage(bgr: np.ndarray) -> QImage:
    success, buf = cv2.imencode(".png", bgr)
    if not success:
        return QImage()
    qimg = QImage()
    qimg.loadFromData(buf.tobytes())
    return qimg


def _content_bbox(gray: np.ndarray, threshold: int = 15) -> tuple[int, int, int, int]:
    """Find bounding box of pixels brighter than threshold (content vs black background)."""
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
    coords = cv2.findNonZero(binary)
    if coords is None:
        return 0, 0, gray.shape[1], gray.shape[0]
    x, y, w, h = cv2.boundingRect(coords)
    pad = 4
    x = max(0, x - pad)
    y = max(0, y - pad)
    w = min(gray.shape[1] - x, w + 2 * pad)
    h = min(gray.shape[0] - y, h + 2 * pad)
    return x, y, w, h


def _make_thumb(filepath: str) -> QImage | None:
    try:
        img = cv2.imread(filepath, cv2.IMREAD_COLOR)
        if img is None:
            return None

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        planes = list(cv2.split(hsv))
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        planes[2] = clahe.apply(planes[2])
        enhanced = cv2.merge(planes)
        bgr = cv2.cvtColor(enhanced, cv2.COLOR_HSV2BGR)

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        x, y, w, h = _content_bbox(gray)
        if w == 0 or h == 0:
            return None
        cropped = bgr[y : y + h, x : x + w]

        old_h, old_w = cropped.shape[:2]
        scale = min(THUMB_SIZE / old_w, THUMB_SIZE / old_h)
        new_w = int(old_w * scale)
        new_h = int(old_h * scale)
        resized = cv2.resize(cropped, (new_w, new_h), interpolation=cv2.INTER_AREA)

        canvas = np.full((THUMB_SIZE, THUMB_SIZE, 3), 48, dtype=np.uint8)
        x_off = (THUMB_SIZE - new_w) // 2
        y_off = (THUMB_SIZE - new_h) // 2
        canvas[y_off : y_off + new_h, x_off : x_off + new_w] = resized
        return _cv2_to_qimage(canvas)
    except Exception:
        log.warning(f"_make_thumb failed for {filepath}")
        return None


class ThumbnailLoader(QThread):
    thumbnail_ready = Signal(int, QImage)

    def __init__(self, items: list[tuple[int, dict]], parent=None):
        super().__init__(parent)
        self._items = items
        self._cancel_flag = False

    def run(self):
        for idx, asset in self._items:
            if self._cancel_flag:
                return
            file = asset.get("file")
            if not file:
                continue
            try:
                cached = _load_cached(file)
                if cached is not None:
                    self.thumbnail_ready.emit(idx, cached)
                    continue

                abspath = os.path.join(ASSETS_ROOT, file)
                if os.path.exists(abspath):
                    img = _make_thumb(abspath)
                    if img is not None:
                        _save_cache(file, img)
                        self.thumbnail_ready.emit(idx, img)
            except Exception:
                log.exception(f"ThumbnailLoader: unhandled error for {file}")

    def cancel(self):
        self._cancel_flag = True
