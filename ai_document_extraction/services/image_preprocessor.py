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
    # Limit OpenMP/OpenCV to a single thread. OpenCV's parallel thread pool
    # crashes in forked worker processes (e.g. the Odoo test runner) where the
    # thread pool state is inherited from the parent, and in containerized
    # environments with restricted thread limits. The environment variable must
    # be set before ``import cv2`` (the lazy import below) so the native OpenMP
    # runtime picks it up.
    os.environ["OMP_NUM_THREADS"] = "1"
    import cv2

    cv2.setNumThreads(1)

    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Could not read image: %s" % image_path)
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
    cv2.imwrite(out_path, binary)
    return out_path
