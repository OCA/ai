# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiAgentTurn(models.Model):
    """The turn of a session in progress, between two of its iterations.

    Each iteration runs in its own worker run: this is what the next one
    needs to go on. Written only by the worker, apart from the session, so
    the user writing the session at the same time (a new message) never
    conflicts with it.
    """

    _name = "ai.agent.turn"
    _description = "AI Agent Turn in Progress"

    session_id = fields.Many2one(
        "ai.agent.session",
        required=True,
        ondelete="cascade",
        index=True,
    )
    message_id = fields.Many2one(
        "mail.message",
        string="Answered Message",
        ondelete="set null",
        help="Last message of the user answered by this turn: the history "
        "sent to the AI stops there.",
    )
    messages = fields.Json(
        help="Messages of the AI and of the tools of the turn so far, after "
        "the history of the conversation.",
    )
    iteration = fields.Integer(
        default=1,
        help="Number of the next iteration, for the maximum allowed.",
    )

    _sql_constraints = [
        (
            "session_id_unique",
            "unique(session_id)",
            "A session has a single turn in progress.",
        ),
    ]
