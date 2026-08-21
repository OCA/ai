# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import os
import re
import tempfile

_IMAGE_EXTENSIONS = ("pdf", "png", "jpg", "jpeg", "gif", "bmp")


def file_extension(filename):
    name = re.sub(r"\s+\(\d+\)$", "", filename or "")
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def is_processable(filename):
    return file_extension(filename) in _IMAGE_EXTENSIONS


def resize_image(path, max_dimension=1280):
    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGB")
        width, height = image.size
        if max(width, height) <= max_dimension:
            return path
        ratio = max_dimension / max(width, height)
        image = image.resize(
            (max(1, round(width * ratio)), max(1, round(height * ratio)))
        )
        resized = f"{path}.resized.png"
        image.save(resized, "PNG")
    try:
        os.unlink(path)
    except OSError:
        pass
    return resized


def prepare_image(attachment):
    """Render attachment (pdf or image) to a resized PNG path."""
    data = attachment.with_context(bin_size=False).raw
    ext = file_extension(attachment.name)
    handle, file_path = tempfile.mkstemp(suffix=f".{ext}")
    os.close(handle)
    try:
        with open(file_path, "wb") as f:
            f.write(data)
        if ext == "pdf":
            from pdf2image import convert_from_path

            images = convert_from_path(file_path, dpi=200, first_page=1, last_page=1)
            if not images:
                raise ValueError("The PDF could not be rendered.")
            png_path = f"{file_path}.png"
            images[0].save(png_path, "PNG")
            try:
                os.unlink(file_path)
            except OSError:
                pass
            file_path = png_path
        return resize_image(file_path)
    except Exception:
        cleanup_tmp(file_path)
        raise


def cleanup_tmp(path):
    import logging

    _logger = logging.getLogger(__name__)
    for candidate in (path, f"{path}.png", f"{path}.resized.png"):
        if os.path.exists(candidate):
            try:
                os.unlink(candidate)
            except OSError:
                _logger.debug("Could not remove tmp %s", candidate)


def mime_from_extension(path):
    ext = os.path.splitext(path)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(ext, "image/png")
