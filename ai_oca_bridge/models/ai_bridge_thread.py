# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class AiBridgeThread(models.AbstractModel):
    _name = "ai.bridge.thread"
    _description = "AI Bridge Mixin"

    # This is an empty shell model maintained for backward compatibility.
    # It prevents other modules from crashing, after improvements to the main
    # AI bridge implementation made this model obsolete.
    #
    # This model can be safely removed once all dependent modules have been
    # updated to use the new AI bridge architecture (e.g. v19+).
