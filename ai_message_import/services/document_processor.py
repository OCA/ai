# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Prepare the files of a conversation before they are sent to the AI.

The AI reads by itself the PDF and the images (``native_types`` of its
client). Word, Excel, CSV and text files are
turned into text first, and so are the emails forwarded as files (.msg,
.eml), whose attachments are stored apart by the conversation. The real type of
every file is taken from its content, not from its name, and the sizes are
bounded.
"""

import io
import logging
import re
import zipfile
from dataclasses import dataclass

from lxml import etree

from odoo import _

from odoo.addons.mail_message_import.services.email_reader import (
    EMAIL_TYPES,
    EML,
    MSG,
    EmailError,
    read_email,
)

from .ai_client import MEDIA_TYPES, PDF, data_part, text_part

_logger = logging.getLogger(__name__)

try:
    import xlrd
except ImportError:  # pragma: no cover
    xlrd = None

MB = 1024 * 1024
MAX_TEXT_CHARS = 200000
MAX_SHEET_ROWS = 5000
MAX_ZIP_MEMBER_SIZE = 50 * MB

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLS = "application/vnd.ms-excel"
DOC = "application/msword"
CSV = "text/csv"
TXT = "text/plain"

# Types turned into text before being sent.
TEXT_TYPES = {DOCX, XLSX, XLS, CSV, TXT}

# Names of the streams of an Outlook email, in the directory of the file.
OUTLOOK_MARK = "__substg1.0_".encode("utf-16-le")
EMAIL_HEADER = re.compile(
    rb"^(Received|Return-Path|From|To|Subject|Date|MIME-Version|Message-ID"
    rb"|Delivered-To|X-[\w-]+):",
    re.IGNORECASE | re.MULTILINE,
)

# Known types that cannot be used, with the code of the reason.
UNSUPPORTED_TYPES = {
    DOC: "doc",
    "audio/amr": "audio",
    "audio/mp4": "audio",
    "video/mp4": "video",
}

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

XML_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, huge_tree=False, remove_comments=True
)


class DocumentError(Exception):
    """The file cannot be used; the first argument is the code of the reason."""


@dataclass
class PreparedDocument:
    label: str
    attachment: object
    filename: str
    mimetype: str
    data: bytes = b""
    text: str = ""
    truncated: bool = False

    def parts(self):
        header = f"Document {self.label} ({self.filename}, {self.mimetype})"
        if self.text:
            note = " The text was truncated." if self.truncated else ""
            return [
                text_part(
                    f"{header}, text extracted by Odoo.{note}\n"
                    f"<<<BEGIN {self.label}>>>\n{self.text}\n<<<END {self.label}>>>"
                )
            ]
        return [
            text_part(f"{header}:"),
            data_part(self.mimetype, self.data, self.filename),
        ]


# (test on the first bytes, type), from the most to the least specific.
SIGNATURES = [
    (lambda head: head.startswith(b"%PDF"), PDF),
    (lambda head: head[:3] == b"\xff\xd8\xff", "image/jpeg"),
    (lambda head: head.startswith(b"\x89PNG\r\n\x1a\n"), "image/png"),
    (lambda head: head[:4] == b"RIFF" and head[8:12] == b"WEBP", "image/webp"),
    (lambda head: head[:4] == b"RIFF" and head[8:12] == b"WAVE", "audio/wav"),
    (lambda head: head.startswith(b"OggS"), "audio/ogg"),
    (
        lambda head: (
            head.startswith(b"ID3")
            or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
        ),
        "audio/mpeg",
    ),
    (lambda head: head.startswith(b"fLaC"), "audio/flac"),
    (lambda head: head[:2] in (b"\xff\xf1", b"\xff\xf9"), "audio/aac"),
    (
        lambda head: head.startswith(b"FORM") and head[8:12] in (b"AIFF", b"AIFC"),
        "audio/aiff",
    ),
    (lambda head: head.startswith(b"#!AMR"), "audio/amr"),
    (lambda head: head[4:11] == b"ftypM4A", "audio/mp4"),
    (lambda head: head[4:8] == b"ftyp", "video/mp4"),
]


def _sniff_zip(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        return None
    if "word/document.xml" in names:
        return DOCX
    if "xl/workbook.xml" in names:
        return XLSX
    return None


def sniff_mimetype(data, filename=""):
    """The type of a file from its first bytes, ``None`` when unknown."""
    head = data[:16]
    name = (filename or "").lower()
    for test, mimetype in SIGNATURES:
        if test(head):
            return mimetype
    if head.startswith(b"PK\x03\x04"):
        return _sniff_zip(data)
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        # Word, Excel and Outlook files share the same container.
        if name.endswith(".msg") or OUTLOOK_MARK in data:
            return MSG
        return XLS if name.endswith(".xls") else DOC
    if b"\x00" not in data[:4096] and (
        name.endswith(".eml") or len(EMAIL_HEADER.findall(data[:4096])) >= 3
    ):
        return EML
    if name.endswith((".csv", ".txt")) and b"\x00" not in data[:4096]:
        return CSV if name.endswith(".csv") else TXT
    return None


def decode_text(data):
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _zip_member(archive, name):
    info = archive.getinfo(name)
    if info.file_size > MAX_ZIP_MEMBER_SIZE:
        raise DocumentError("uncompressed")
    return archive.read(name)


def _xml(data):
    return etree.fromstring(data, parser=XML_PARSER)


def _docx_paragraph(paragraph):
    chunks = []
    for node in paragraph.iter(W_NS + "t", W_NS + "tab", W_NS + "br"):
        if node.tag == W_NS + "t":
            chunks.append(node.text or "")
        else:
            chunks.append("\t")
    return "".join(chunks).strip()


def _docx_blocks(root):
    lines = []
    body = root.find(W_NS + "body")
    for block in body if body is not None else root:
        if block.tag == W_NS + "p":
            lines.append(_docx_paragraph(block))
        elif block.tag == W_NS + "tbl":
            for row in block.iter(W_NS + "tr"):
                cells = [
                    " ".join(_docx_paragraph(par) for par in cell.iter(W_NS + "p"))
                    for cell in row.iter(W_NS + "tc")
                ]
                lines.append(" | ".join(cell.strip() for cell in cells))
    return [line for line in lines if line.strip(" |")]


def extract_docx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        lines = []
        for name in sorted(n for n in names if re.match(r"word/header\d*\.xml$", n)):
            lines += _docx_blocks(_xml(_zip_member(archive, name)))
        lines += _docx_blocks(_xml(_zip_member(archive, "word/document.xml")))
        for name in sorted(n for n in names if re.match(r"word/footer\d*\.xml$", n)):
            lines += _docx_blocks(_xml(_zip_member(archive, name)))
    return "\n".join(lines)


def _column_index(reference):
    letters = re.match(r"[A-Z]+", reference or "")
    index = 0
    for letter in letters.group(0) if letters else "":
        index = index * 26 + ord(letter) - 64
    return max(index - 1, 0)


def _format_cell(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def extract_xlsx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = _xml(_zip_member(archive, "xl/sharedStrings.xml"))
            shared = [
                "".join(node.text or "" for node in item.iter(S_NS + "t"))
                for item in root.iter(S_NS + "si")
            ]
        targets = {}
        if "xl/_rels/workbook.xml.rels" in names:
            rels = _xml(_zip_member(archive, "xl/_rels/workbook.xml.rels"))
            targets = {
                rel.get("Id"): rel.get("Target")
                for rel in rels.iter(REL_NS + "Relationship")
            }
        workbook = _xml(_zip_member(archive, "xl/workbook.xml"))
        lines, rows_read = [], 0
        for sheet in workbook.iter(S_NS + "sheet"):
            target = (targets.get(sheet.get(R_NS + "id")) or "").lstrip("/")
            path = target if target.startswith("xl/") else f"xl/{target}"
            if path not in names:
                continue
            lines.append(f"Sheet: {sheet.get('name')}")
            for row in _xml(_zip_member(archive, path)).iter(S_NS + "row"):
                rows_read += 1
                if rows_read > MAX_SHEET_ROWS:
                    break
                cells = {}
                for cell in row.iter(S_NS + "c"):
                    kind = cell.get("t")
                    value_node = cell.find(S_NS + "v")
                    value = value_node.text if value_node is not None else ""
                    if kind == "s" and value:
                        value = shared[int(value)] if int(value) < len(shared) else ""
                    elif kind == "inlineStr":
                        value = "".join(n.text or "" for n in cell.iter(S_NS + "t"))
                    cells[_column_index(cell.get("r"))] = (value or "").strip()
                if any(cells.values()):
                    width = max(cells) + 1
                    lines.append(" | ".join(cells.get(i, "") for i in range(width)))
    return "\n".join(lines)


def extract_xls(data):
    if xlrd is None:
        raise DocumentError("xlrd")
    book = xlrd.open_workbook(file_contents=data, on_demand=True)
    lines, rows_read = [], 0
    for sheet in book.sheets():
        lines.append(f"Sheet: {sheet.name}")
        for index in range(sheet.nrows):
            rows_read += 1
            if rows_read > MAX_SHEET_ROWS:
                break
            values = [_format_cell(value) for value in sheet.row_values(index)]
            if any(values):
                lines.append(" | ".join(values))
    return "\n".join(lines)


EXTRACTORS = {
    DOCX: extract_docx,
    XLSX: extract_xlsx,
    XLS: extract_xls,
    CSV: decode_text,
    TXT: decode_text,
}


class DocumentProcessor:
    """:param client: the client of the AI, which tells the files it reads by
    itself; without it, any of ``MEDIA_TYPES``."""

    def __init__(self, env, max_file_size_mb=20, max_total_size_mb=50, client=None):
        self.env = env
        self.max_file_bytes = max_file_size_mb * MB
        self.max_total_bytes = max_total_size_mb * MB
        self.native_types = client.native_types if client else MEDIA_TYPES

    def prepare(self, entries):
        """Prepare the files of a conversation.

        :param entries: ``(label, attachment)`` pairs, in the order of the
            conversation.
        :return: ``(documents, issues)``; every issue is a
            ``(label, attachment, reason)`` of a file left out.
        """
        documents, issues, total = [], [], 0
        for label, attachment in entries:
            try:
                document = self._prepare_one(label, attachment)
            except DocumentError as exc:
                issues.append((label, attachment, self._reason(exc.args[0])))
                continue
            except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
                # A corrupt file must not block the rest of the conversation.
                _logger.info("Cannot read attachment %s: %s", attachment.id, exc)
                issues.append((label, attachment, self._reason("damaged")))
                continue
            size = len(document.data) + len(document.text.encode())
            if total + size > self.max_total_bytes:
                issues.append((label, attachment, self._reason("total")))
                continue
            total += size
            documents.append(document)
        return documents, issues

    def _prepare_one(self, label, attachment):
        data = attachment.raw or b""
        if not data:
            raise DocumentError("empty")
        if len(data) > self.max_file_bytes:
            raise DocumentError("size")
        mimetype = sniff_mimetype(data, attachment.name)
        if mimetype in UNSUPPORTED_TYPES:
            raise DocumentError(UNSUPPORTED_TYPES[mimetype])
        if mimetype in MEDIA_TYPES:
            if mimetype not in self.native_types:
                raise DocumentError("provider")
            return PreparedDocument(label, attachment, attachment.name, mimetype, data)
        if mimetype and mimetype.startswith("audio/"):
            # Voice notes: the AI connection is given no audio.
            raise DocumentError("provider")
        if mimetype in EMAIL_TYPES:
            # Its attachments are documents of their own, see the conversation.
            try:
                text = read_email(data, mimetype).text
            except EmailError as exc:
                raise DocumentError(exc.args[0]) from exc
            return PreparedDocument(
                label,
                attachment,
                attachment.name,
                mimetype,
                text=text[:MAX_TEXT_CHARS],
                truncated=len(text) > MAX_TEXT_CHARS,
            )
        if mimetype in TEXT_TYPES:
            text = EXTRACTORS[mimetype](data).strip()
            if not text:
                raise DocumentError("no_text")
            truncated = len(text) > MAX_TEXT_CHARS
            return PreparedDocument(
                label,
                attachment,
                attachment.name,
                mimetype,
                text=text[:MAX_TEXT_CHARS],
                truncated=truncated,
            )
        raise DocumentError("type")

    def _reason(self, code):
        """Why a file was left out, for the person reviewing it."""
        reasons = {
            "empty": _("The file is empty."),
            "size": _(
                "The file exceeds the maximum size of %(size)s MB.",
                size=self.max_file_bytes // MB,
            ),
            "total": _(
                "The files of the conversation exceed the size allowed for one "
                "analysis."
            ),
            "doc": _(
                "Old Word documents (.doc) are not supported, a .docx or a PDF is "
                "needed."
            ),
            "audio": _("This audio format is not supported."),
            "provider": _("The AI does not read this type of file."),
            "video": _("Videos are not processed."),
            "no_text": _("The document has no readable text."),
            "uncompressed": _("The document is too large once uncompressed."),
            "xlrd": _("The xlrd library is needed to read .xls files."),
            "msg_library": _(
                "The extract-msg library is needed to read Outlook emails (.msg)."
            ),
            "damaged": _("The file is damaged or unreadable."),
        }
        return reasons.get(code) or _("The file type is not supported.")
