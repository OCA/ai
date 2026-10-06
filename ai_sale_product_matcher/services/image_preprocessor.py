# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import os
import re
import tempfile

_logger = logging.getLogger(__name__)

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
        _logger.debug("Could not remove tmp file %s", path, exc_info=True)
    return resized


def prepare_image(attachment):
    """Backward compat: return first page only."""
    paths = prepare_images(attachment, max_pages=1)
    return paths[0] if paths else None


def prepare_images(attachment, max_pages=4):
    """Render attachment to list of resized PNG paths (multi-page PDF support)."""
    data = attachment.with_context(bin_size=False).raw
    ext = file_extension(attachment.name)
    handle, file_path = tempfile.mkstemp(suffix=f".{ext}")
    os.close(handle)
    tmp_paths = []
    try:
        with open(file_path, "wb") as f:
            f.write(data)
        if ext == "pdf":
            from pdf2image import convert_from_path

            try:
                # Get page count to limit
                from pdf2image import pdfinfo_from_path

                info = pdfinfo_from_path(file_path)
                total_pages = int(info.get("Pages", 1))
            except Exception:
                total_pages = max_pages
            pages_to_render = min(total_pages, max_pages)
            images = convert_from_path(
                file_path, dpi=200, first_page=1, last_page=pages_to_render
            )
            if not images:
                raise ValueError("The PDF could not be rendered.")
            try:
                os.unlink(file_path)
            except OSError:
                _logger.debug("Could not remove tmp file %s", file_path, exc_info=True)
            for idx, image in enumerate(images):
                png_path = f"{file_path}.page{idx}.png"
                image.save(png_path, "PNG")
                resized = resize_image(png_path)
                tmp_paths.append(resized)
            return tmp_paths
        else:
            resized = resize_image(file_path)
            return [resized]
    except Exception:
        cleanup_tmp(file_path)
        for p in tmp_paths:
            cleanup_tmp(p)
        raise


def extract_text_from_pdf(attachment):
    """Extract text from PDF via pdfminer as fallback (for spec sheets)."""
    if file_extension(attachment.name) != "pdf":
        return ""
    data = attachment.with_context(bin_size=False).raw
    handle, file_path = tempfile.mkstemp(suffix=".pdf")
    os.close(handle)
    try:
        with open(file_path, "wb") as f:
            f.write(data)
        try:
            from pdfminer.high_level import extract_text

            text = extract_text(file_path) or ""
            return text.strip()
        except ImportError:
            return ""
        except Exception:
            return ""
    finally:
        try:
            os.unlink(file_path)
        except OSError:
            _logger.debug("Could not remove tmp file %s", file_path, exc_info=True)


def cleanup_tmp(path):
    for candidate in (path, f"{path}.png", f"{path}.resized.png"):
        if os.path.exists(candidate):
            try:
                os.unlink(candidate)
            except OSError:
                _logger.debug("Could not remove tmp %s", candidate)
    # Also try page variants
    for i in range(10):
        cand = f"{path}.page{i}.png"
        if os.path.exists(cand):
            try:
                os.unlink(cand)
            except OSError:
                _logger.debug("Could not remove tmp %s", cand, exc_info=True)
        cand2 = f"{cand}.resized.png"
        if os.path.exists(cand2):
            try:
                os.unlink(cand2)
            except OSError:
                _logger.debug("Could not remove tmp %s", cand2, exc_info=True)


def mime_from_extension(path):
    ext = os.path.splitext(path)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(ext, "image/png")
