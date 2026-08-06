# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import threading

_PADDLE_LANG_MAP = {
    "tur+eng": "latin",
    "tur": "latin",
    "eng": "en",
}

_thread_local = threading.local()


def _get_ocr(ocr_language):
    """Create (once per thread) a PaddleOCR instance for the given language."""
    import paddleocr

    lang = _PADDLE_LANG_MAP.get(ocr_language, "latin")
    ocr = getattr(_thread_local, "ocr", None)
    ocr_lang = getattr(_thread_local, "ocr_lang", None)
    if ocr is None or ocr_lang != lang:
        _thread_local.ocr = paddleocr.PaddleOCR(lang=lang, use_angle_cls=True)
        _thread_local.ocr_lang = lang
    return _thread_local.ocr


def extract_text_with_layout(image_path, ocr_language="tur+eng", image_height=None):
    """Run OCR and tag each line with a positional [HEADER]/[BODY]/[FOOTER].

    The top 20% of the page is tagged [HEADER], the bottom 20% [FOOTER] and
    everything in between [BODY], based on the vertical center of each text
    line. This lets the LLM ignore logo/slogan texts found in the header.

    Returns one "[TAG] text" line per OCR line, joined by newlines.
    """
    import cv2

    if image_height is None:
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not read image: {image_path}")
        image_height = img.shape[0]
    ocr = _get_ocr(ocr_language)
    result = ocr.ocr(image_path, cls=True)
    lines = []
    if not result:
        return ""
    for page in result:
        if not page:
            continue
        for box, (text, _score) in page:
            ys = [point[1] for point in box]
            center_y = sum(ys) / len(ys)
            ratio = center_y / float(image_height)
            if ratio < 0.2:
                tag = "[HEADER]"
            elif ratio > 0.8:
                tag = "[FOOTER]"
            else:
                tag = "[BODY]"
            if text and text.strip():
                lines.append(f"{tag} {text.strip()}")
    return "\n".join(lines)
