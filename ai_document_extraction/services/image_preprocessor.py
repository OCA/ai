# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import os
import tempfile

MAX_DIM = 2000


def preprocess_image(image_path):
    """Enhance and resize an image for OCR.

    Converts to grayscale, applies CLAHE contrast enhancement, denoises with a
    Gaussian blur, binarizes with an Otsu threshold and resizes down (keeping
    aspect ratio) if the longest side exceeds ``MAX_DIM``.

    Returns the path to the processed PNG. The caller must delete it.
    """
    # Limit the OpenMP runtime to a single thread before OpenCV is imported.
    # In forked worker processes (e.g. the Odoo test runner) the inherited
    # OpenMP thread-pool state crashes at import time with a SIGSEGV; the env
    # variable must be set before ``import cv2`` and cv2.setNumThreads(1) alone
    # does NOT prevent it.
    os.environ["OMP_NUM_THREADS"] = "1"
    import cv2

    cv2.setNumThreads(1)

    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    height, width = binary.shape
    if max(width, height) > MAX_DIM:
        scale = MAX_DIM / float(max(width, height))
        binary = cv2.resize(
            binary,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_AREA,
        )
    handle, out_path = tempfile.mkstemp(suffix=".png")
    os.close(handle)
    if not cv2.imwrite(out_path, binary):
        os.unlink(out_path)
        raise ValueError(f"Could not write processed image: {out_path}")
    return out_path
