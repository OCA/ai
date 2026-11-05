# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.tools import sql

try:
    import openai
except ImportError:
    openai = None


class IrModelFieldVector(models.Model):
    """
    Model to store vector configuration for ir.model.fields of type computed_vector
    """

    _name = "ir.model.field.vector"
    _description = "Ir Model Field Vector"
    _rec_name = "field_id"

    field_id = fields.Many2one(
        "ir.model.fields",
        ondelete="cascade",
        required=True,
        domain=[
            ("ttype", "=", "computed_vector"),
            ("store", "=", True),
        ],
    )
    dimensions = fields.Integer()
    vector_method = fields.Selection(
        selection=lambda self: self._get_vector_methods(),
        required=True,
    )
    search_prefix = fields.Text(
        help="""This prefix will be added to the text before encoding it for search.
        It can be used to give specific instructions to the embedding model,
        like 'Represent this sentence for searching relevant passages: '"""
    )
    openai_url = fields.Char(
        string="OpenAI URL", default="https://api.openai.com/v1/embeddings"
    )
    openai_model = fields.Char(string="OpenAI Model", default="text-embedding-3-small")
    openai_api_key = fields.Char(string="OpenAI API Key", groups="base.group_system")
    fastembed_model = fields.Char(
        string="FastEmbed Model", default="BAAI/bge-small-en-v1.5"
    )
    compute = fields.Text(compute="_compute_compute")

    _sql_constraints = [
        (
            "field_id_uniq",
            "unique (field_id)",
            "A vector field should be associated to a single ir.model.fields record.",
        )
    ]

    @api.depends("field_id")
    def _compute_compute(self):
        for record in self:
            if record.field_id:
                record.compute = (
                    self.env[record.field_id.model]
                    .sudo()
                    ._fields[record.field_id.name]
                    .compute
                )
            else:
                record.compute = False

    def compute_values(self):
        self.ensure_one()
        if not self.compute:
            return
        getattr(self.env[self.field_id.model].search([]), self.compute)()

    def _get_vector_methods(self):
        methods = []
        if openai:
            methods.append(("openai", "OpenAI"))
        return methods

    def update_column(self):
        self.ensure_one()
        model = self.env[self.field_id.model].browse()
        columns = sql.table_columns(self.env.cr, model._table)
        column = columns.get(self.field_id.name)
        model._fields[self.field_id.name].update_db_column(model, column)

    def _encode_vector(self, data, is_search=False):
        """
        It should allways return a list of vectors, even if the input is a single one.
        """
        if is_search and self.search_prefix:
            data = self.search_prefix + data
        return getattr(self, f"_encode_vector_{self.vector_method}")(data)

    def _encode_vector_openai(self, text):
        openai_client = openai.OpenAI(**self.sudo()._get_openai_client_parameters())
        response = openai_client.embeddings.create(model=self.openai_model, input=text)
        return [embedding.embedding for embedding in response.data]

    def _get_openai_client_parameters(self):
        params = {}
        if self.openai_url:
            params["base_url"] = self.openai_url
        if self.openai_api_key:
            params["api_key"] = self.openai_api_key
        return params
