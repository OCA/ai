# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


class AiConnectionClient:
    def handle_message(self, messages=None, **kwargs):
        """Handle a message from the AI system.
        Will return a dict with the following information:
        {
            "message": "",
            "tool_calls": [
                {
                    "name": "",
                    "arguments": {},
                }
            ]
        }
        """
        raise NotImplementedError("Subclasses must implement this method")
