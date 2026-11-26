# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Products chosen by the AI for the lines no exact rule identified.

Customers and vendors write the products their own way ("10 c mezclum", "kilo
canonicos 2x500"), so the exact rules of ``matching.py`` often find nothing.
For those lines the AI receives the closest products of the catalogue, with the
times the partner took each one in the last year, and chooses one only when the
line clearly designates it. The choice is noted on the order, to be checked
before confirming it, and learned when the order is confirmed.
"""

import json
import re
from difflib import SequenceMatcher

from odoo.osv.expression import OR as Domain_or

from .ai_client import text_part
from .matching import PACKAGING_WORDS, UOM_ALIASES, accent_like, singular
from .prompts import PROMPT_PRODUCT_CHOICE, fill_placeholders
from .tools import normalize_text

#: Catalogues up to this size are compared whole; bigger ones are searched by
#: the words of the line first.
FULL_SCAN_LIMIT = 5000
#: Candidates sent to the AI per line.
CANDIDATES_PER_LINE = 8
#: Similarity for two words to count as the same one ("canonicos", "canonigos").
WORD_SIMILARITY = 0.8

# Words that tell nothing of the product itself: units, packagings and links.
STOP_WORDS = (
    {
        "de",
        "del",
        "la",
        "las",
        "el",
        "los",
        "con",
        "sin",
        "para",
        "por",
        "en",
        "al",
        "una",
        "uno",
        "the",
        "and",
        "with",
        "for",
    }
    | set(PACKAGING_WORDS)
    | set(PACKAGING_WORDS.values())
    | {word for words in UOM_ALIASES.values() for word in words}
)

TOKEN = re.compile(r"[a-z]+|\d+")

CHOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "product": {"type": "integer"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string"},
                },
                "required": ["line", "product", "confidence", "reason"],
            },
        }
    },
    "required": ["lines"],
}


def tokens(text):
    """Significant words and numbers of ``text``."""
    words, numbers = [], set()
    for token in TOKEN.findall(normalize_text(text)):
        if token.isdigit():
            numbers.add(token)
        elif len(token) > 2 and singular(token) not in STOP_WORDS:
            words.append(token)
    return words, numbers


def same_word(word, other):
    """Whether two words are the same one, also misspelled."""
    if word == other:
        return 1.0
    if word[0] != other[0] or abs(len(word) - len(other)) > 3:
        return 0.0
    ratio = SequenceMatcher(None, word, other).ratio()
    return ratio if ratio >= WORD_SIMILARITY else 0.0


def similarity(line_tokens, name_tokens):
    """How much a product name looks like a line: the share of the words of the
    line found in the name, plus a little for each number in common."""
    words, numbers = line_tokens
    names, name_numbers = name_tokens
    if not words or not names:
        return 0.0
    found = sum(max(same_word(word, name) for name in names) for word in words)
    if not found:
        return 0.0
    return found / len(words) + 0.1 * len(numbers & name_numbers)


class ProductChooser:
    """Candidates of the lines without product, and the choice of the AI.

    :param matcher: the ``ProductMatcher`` of the quote: its products are the
        ones that can be ordered.
    :param role: ``customer`` or ``vendor``, for the instructions.
    :param usual: ``{product: times}`` the partner took each product in the
        last year.
    """

    def __init__(self, env, matcher, role, usual):
        self.env = env
        self.matcher = matcher
        self.role = role
        self.usual = usual
        self._catalogue = None
        self._name_tokens = {}
        # Tokens spent by the request to the AI, for their debit.
        self.tokens = 0

    @staticmethod
    def _name(product):
        """Name of ``product`` with its variant, without its reference."""
        return product.with_context(display_default_code=False).display_name

    def _products(self, domain=None, limit=None):
        return self.matcher.Product.search(
            self.matcher._product_domain() + (domain or []), limit=limit
        )

    def _pool(self, words):
        """Products to compare with a line: the whole catalogue when it is
        small, otherwise the ones with a word of the line in their name."""
        if self._catalogue is None:
            count = self.matcher.Product.search_count(self.matcher._product_domain())
            self._catalogue = self._products() if count <= FULL_SCAN_LIMIT else False
        if self._catalogue is not False:
            return self._catalogue
        if not words:
            return self.matcher.Product
        return self._products(
            Domain_or([[("name", "ilike", accent_like(word))] for word in words]),
            limit=500,
        )

    def candidates(self, values, extra=None):
        """Products that look like the line ``values``, the most alike first.

        :param extra: products that must be candidates, e.g. the ones that
            matched the line ambiguously.
        """
        line_tokens = tokens(values.get("description") or "")
        scores = {}
        for product in self._pool(line_tokens[0]):
            if product.id not in self._name_tokens:
                self._name_tokens[product.id] = tokens(self._name(product))
            score = similarity(line_tokens, self._name_tokens[product.id])
            if score:
                # The products the partner takes go first when they look alike.
                scores[product] = score + (0.05 if product in self.usual else 0.0)
        best = sorted(scores, key=lambda p: (-scores[p], p.id))[:CANDIDATES_PER_LINE]
        found = self.matcher.Product.browse([p.id for p in best])
        return (extra or self.matcher.Product) | found

    def choose(self, client, lines, min_confidence):
        """Ask the AI for the product of each line.

        :param lines: ``[(key, values, candidates)]``; ``values`` with the
            ``description``, ``product_code``, ``uom`` and ``quantity`` of the line.
        :return: ``{key: (product, confidence, reason)}``, only for the lines
            with a candidate chosen with at least ``min_confidence``.
        """
        request = [
            {
                "line": index,
                "text": values.get("description") or "",
                "code": values.get("product_code") or "",
                "unit": values.get("uom") or "",
                "quantity": values.get("quantity"),
                "candidates": [
                    {
                        "id": product.id,
                        "reference": product.default_code or "",
                        "name": self._name(product),
                        "unit": product.uom_id.name,
                        "times_taken": self.usual.get(product, 0),
                    }
                    for product in candidates
                ],
            }
            for index, (_key, values, candidates) in enumerate(lines, 1)
        ]
        instruction = fill_placeholders(
            self.env["ai.message.import.prompt"]._content(PROMPT_PRODUCT_CHOICE),
            role=self.role,
            lang=self.env.lang or "en_US",
        )
        data, _raw_text, self.tokens = client.generate_json(
            instruction,
            [text_part(json.dumps({"lines": request}, ensure_ascii=False))],
            CHOICE_SCHEMA,
        )
        answers = data.get("lines") if isinstance(data, dict) else None
        choices = {}
        for answer in answers if isinstance(answers, list) else []:
            if not isinstance(answer, dict):
                continue
            index, confidence = answer.get("line"), answer.get("confidence")
            if not isinstance(index, int) or not 1 <= index <= len(lines):
                continue
            if not isinstance(confidence, int | float) or confidence < min_confidence:
                continue
            key, _values, candidates = lines[index - 1]
            product = candidates.filtered(lambda p, a=answer: p.id == a.get("product"))
            if product:
                reason = str(answer.get("reason") or "").strip()[:300]
                choices[key] = (product, float(confidence), reason)
        return choices
