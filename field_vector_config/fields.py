# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.addons.field_vector.fields import Vector


def split_text_chunks(text, max_words=350, overlap=50):
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        chunk = " ".join(words[start : start + max_words])
        chunks.append(chunk)
        start += max_words - overlap
    return chunks


class ComputedVector(Vector):
    type = "computed_vector"

    def __init__(
        self,
        dimensions=10,
        **kwargs,
    ):
        # We set a default dimensions value
        super().__init__(dimensions=dimensions, **kwargs)

    @property
    def column_type(self):
        return ("vector", "vector")

    def vector_dimensions(self, model):
        dimensions = (
            model.env["ir.model.fields"]
            .sudo()
            .search(
                [("model", "=", model._name), ("name", "=", self.name)],
                limit=1,
            )
            .vector_configuration_ids.dimensions
        )
        return dimensions or super().vector_dimensions(model)
