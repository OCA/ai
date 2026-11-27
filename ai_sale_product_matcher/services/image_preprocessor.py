# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import io
import logging
import re

from pdf2image import convert_from_bytes
from PIL import Image

_logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = ("pdf", "png", "jpg", "jpeg", "gif", "bmp")


def file_extension(filename):
    name = re.sub(r"\s+\(\d+\)$", "", filename or "")
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def is_processable(filename):
    return file_extension(filename) in _IMAGE_EXTENSIONS


def _resize_pil_image_to_png_bytes(image, max_dimension=1280):
    image = image.convert("RGB")
    width, height = image.size
    if max(width, height) > max_dimension:
        ratio = max_dimension / max(width, height)
        image = image.resize(
            (max(1, round(width * ratio)), max(1, round(height * ratio)))
        )
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def render_attachment_images(env, attachment, max_pages=4, max_dimension=1280):
    """Render an attachment into in-memory PNG ir.attachment records."""
    data = attachment.with_context(bin_size=False).raw
    ext = file_extension(attachment.name)
    base_name = (attachment.name or "document").rsplit(".", 1)[0]
    rendered = env["ir.attachment"]
    if ext == "pdf" or attachment.mimetype == "application/pdf":
        images = convert_from_bytes(data, dpi=200, first_page=1, last_page=max_pages)
        if not images:
            raise ValueError("The PDF could not be rendered.")
        for index, image in enumerate(images, start=1):
            png_bytes = _resize_pil_image_to_png_bytes(
                image, max_dimension=max_dimension
            )
            rendered |= env["ir.attachment"].create(
                {
                    "name": f"{base_name}_page_{index}.png",
                    "datas": base64.b64encode(png_bytes),
                    "mimetype": "image/png",
                }
            )
        return rendered
    with Image.open(io.BytesIO(data)) as image:
        png_bytes = _resize_pil_image_to_png_bytes(image, max_dimension=max_dimension)
    rendered |= env["ir.attachment"].create(
        {
            "name": f"{base_name}.png",
            "datas": base64.b64encode(png_bytes),
            "mimetype": "image/png",
        }
    )
    return rendered


def extract_text_from_pdf(attachment):
    """Extract text from PDF in memory via pdfminer when installed."""
    if (
        file_extension(attachment.name) != "pdf"
        and attachment.mimetype != "application/pdf"
    ):
        return ""
    data = attachment.with_context(bin_size=False).raw
    if not data:
        return ""
    try:
        from pdfminer.high_level import extract_text

        text = extract_text(io.BytesIO(data)) or ""
        return text.strip()
    except Exception:
        _logger.debug("PDF text extraction unavailable or failed", exc_info=True)
        return ""
