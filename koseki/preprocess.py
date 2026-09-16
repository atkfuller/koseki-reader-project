"""Preprocessing for Japanese koseki scans.

These particular scans are certified municipal copies printed on security paper.
Three things sit between the ink and the OCR engine:

  1. a cyan/teal decorative gradient plus an orange city mascot,
  2. a light-grey "copy-evident" ghost pattern woven through the page,
  3. repeated pale text of the city name tiled across the background.

(1) is *chromatic* and (2)/(3) are *achromatic but light*, so they come off in
two different ways: a max-channel collapse kills anything coloured, and a local
(Sauvola) threshold kills anything lighter than its neighbourhood.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


def decolor(bgr: np.ndarray) -> np.ndarray:
    """Collapse to greyscale by taking the brightest channel per pixel.

    Ink is neutral and dark, so max(B,G,R) stays dark. Anything with colour has
    at least one bright channel -- cyan is bright in G and B, the orange seal is
    bright in R -- so both wash out to near-white. This is much better here than
    a luminance conversion, which keeps the teal as mid-grey.
    """
    return bgr.max(axis=2)


def sauvola(gray: np.ndarray, window: int = 51, k: float = 0.2, r: float = 128.0) -> np.ndarray:
    """Sauvola local threshold: T = m * (1 + k * (s/r - 1)).

    Better than a global Otsu threshold on these pages because illumination and
    background density vary a lot across a single scan. Returns 0/255 uint8.
    """
    if window % 2 == 0:
        window += 1
    g = gray.astype(np.float32)
    mean = cv2.boxFilter(g, cv2.CV_32F, (window, window), normalize=True)
    sq = cv2.boxFilter(g * g, cv2.CV_32F, (window, window), normalize=True)
    std = np.sqrt(np.maximum(sq - mean * mean, 0))
    thresh = mean * (1 + k * (std / r - 1))
    return np.where(g > thresh, 255, 0).astype(np.uint8)


def deskew_angle(binary: np.ndarray, limit: float = 8.0) -> float:
    """Estimate page skew in degrees from the dominant near-horizontal lines.

    Koseki pages are ruled tables, so the ruling gives a much cleaner skew signal
    than text baselines do -- especially for vertical Japanese, where there are
    no baselines to speak of.
    """
    edges = cv2.Canny(255 - binary, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 720, threshold=200)
    if lines is None:
        return 0.0
    angles = []
    for rho_theta in lines[:, 0]:
        deg = np.degrees(rho_theta[1]) - 90.0  # 0 for a perfectly horizontal line
        if abs(deg) <= limit:
            angles.append(deg)
    return float(np.median(angles)) if angles else 0.0


def rotate(img: np.ndarray, angle: float, fill: int = 255) -> np.ndarray:
    if abs(angle) < 0.05:
        return img
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        img, m, (w, h), flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=fill,
    )


@dataclass
class Prepped:
    """Every stage kept, so a benchmark can feed each one to OCR and compare."""
    original: np.ndarray   # BGR
    gray: np.ndarray       # luminance, the naive baseline
    decolored: np.ndarray  # max-channel, watermark suppressed
    binary: np.ndarray     # decolored + Sauvola
    deskewed: np.ndarray   # binary, rotated flat
    angle: float

    def stages(self) -> dict[str, np.ndarray]:
        return {
            "gray": self.gray,
            "decolored": self.decolored,
            "binary": self.binary,
            "deskewed": self.deskewed,
        }


def prep(path: str | Path, window: int = 51, k: float = 0.2) -> Prepped:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(path)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    dec = decolor(bgr)
    binary = sauvola(dec, window=window, k=k)
    angle = deskew_angle(binary)
    return Prepped(bgr, gray, dec, binary, rotate(binary, angle), angle)
