"""OCR helpers for bank receipt images."""

from __future__ import annotations

import io
import logging

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

logger = logging.getLogger(__name__)


def _preprocess(image: Image.Image) -> Image.Image:
    img = image.convert("L")
    img = ImageOps.autocontrast(img)
    img = img.filter(ImageFilter.SHARPEN)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.6)
    # Upscale small images for better OCR
    w, h = img.size
    if max(w, h) < 1200:
        scale = 1200 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    return img


def extract_text_from_image(image_bytes: bytes) -> str:
    """Run Tesseract OCR (Persian + English) on a receipt image."""
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract نصب نشده است") from exc

    image = Image.open(io.BytesIO(image_bytes))
    processed = _preprocess(image)

    configs = [
        "-l fas+eng --psm 6",
        "-l fas+eng --psm 4",
        "-l fas --psm 6",
    ]
    texts: list[str] = []
    for cfg in configs:
        try:
            text = pytesseract.image_to_string(processed, config=cfg)
            if text and text.strip():
                texts.append(text.strip())
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCR config failed (%s): %s", cfg, exc)

    if not texts:
        # Fallback without preprocessing
        try:
            texts.append(
                pytesseract.image_to_string(image, config="-l fas+eng --psm 6").strip()
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("OCR completely failed: %s", exc)
            return ""

    # Prefer the longest readable result
    return max(texts, key=lambda t: len(t.replace(" ", "")))
