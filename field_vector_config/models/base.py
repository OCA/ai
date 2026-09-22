# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import sql

from ..fields import ComputedVector


class Base(models.AbstractModel):
    _inherit = "base"

    @api.model
    @api.readonly
    @api.returns("self")
    def search_vector(self, field_name, data, domain=None, limit=5, minim=0.5):
        if domain is None:
            domain = []
        if not isinstance(self._fields[field_name], ComputedVector):
            raise UserError(f"Field {field_name} is not a computed_vector field")
        to_search = self._encode_vector(field_name, data, is_search=True)[0]
        query = self._search(domain, limit=limit)
        distance = sql.SQL(
            "%s <=> %s::vector",
            self._field_to_sql(self._table, field_name, query),
            to_search,
        )
        sql_terms = [
            self._field_to_sql(self._table, "id", "query"),
            sql.SQL("%s as distance", distance),
        ]
        query.order = "distance ASC"
        if minim:
            query.add_where(sql.SQL("%s < %s", distance, minim))
        self.env.cr.execute(query.select(*sql_terms))
        return self.browse([row[0] for row in self.env.cr.fetchall()])

    @api.model
    @api.readonly
    @api.returns("self")
    def search_vector_grouped(
        self, field_name, data, final_field, domain=None, limit=5, minim=0.5
    ):
        if domain is None:
            domain = []
        if not isinstance(self._fields[field_name], ComputedVector):
            raise UserError(f"Field {field_name} is not a computed_vector field")
        if not isinstance(self._fields[final_field], fields.Many2one):
            raise UserError(f"Field {final_field} is not a Many2one field")
        to_search = self._encode_vector(field_name, data, is_search=True)[0]
        query = self._search(domain, limit=limit)
        distance = sql.SQL(
            "MIN(%s <=> %s::vector)",
            self._field_to_sql(self._table, field_name, query),
            to_search,
        )
        sql_terms = [
            self._field_to_sql(self._table, final_field, "query"),
            sql.SQL("%s as distance", distance),
        ]
        query.order = "distance ASC"
        query.groupby = self._field_to_sql(self._table, final_field, query)
        if minim:
            query.having = sql.SQL("%s < %s", distance, minim)
        self.env.cr.execute(query.select(*sql_terms))
        rows = self.env.cr.fetchall()
        return self[final_field].browse([row[0] for row in rows])

    def _encode_vector(self, field_name, data, is_search=False):
        config = (
            self.env["ir.model.fields"]
            .sudo()
            .search(
                [("model", "=", self._name), ("name", "=", field_name)],
                limit=1,
            )
            .vector_configuration_ids
        )
        if not config:
            raise UserError(f"Field {field_name} is not configured")
        return config._encode_vector(data, is_search=is_search)
