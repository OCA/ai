# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The prompts the module asks for (``ai.message.import.prompt``) and their
placeholders. Their text is data: the module never writes it."""

# Reading the conversations, with {types} and {version}.
PROMPT_EXTRACTION = "extraction"
# Choosing the products of the lines, with {role} and {lang}.
PROMPT_PRODUCT_CHOICE = "product_choice"
# When a document is of a type and who its partner is: see document_type_code.
PROMPT_DOCUMENT_TYPE = "document_type."


def document_type_code(key):
    """Code of the description of the document type ``key``."""
    return f"{PROMPT_DOCUMENT_TYPE}{key}"


def fill_placeholders(text, **values):
    """``text`` with its ``{name}`` placeholders replaced by ``values``.

    Only the given names are replaced: any other brace of the prompt is kept.
    """
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text
