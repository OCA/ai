# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class McpPrompt(models.Model):
    _name = "mcp.prompt"
    _description = "MCP Prompt"
    _order = "server_id, name"

    name = fields.Char(string="Prompt Name", required=True, index=True)
    server_id = fields.Many2one(
        "mcp.server", string="Server", required=True, ondelete="cascade", index=True
    )
    server_state = fields.Selection(
        related="server_id.state", string="Server Status", readonly=True
    )
    description = fields.Text()
    arguments = fields.Text(
        help="JSON array of prompt arguments",
        default="[]",
    )

    _sql_constraints = [
        (
            "server_name_uniq",
            "unique(server_id, name)",
            "Prompt name must be unique per server!",
        )
    ]

    @api.constrains("arguments")
    def _check_arguments(self):
        for record in self:
            if record.arguments:
                try:
                    args_json = json.loads(record.arguments)
                    if not isinstance(args_json, list):
                        raise ValidationError(_("Arguments must be a JSON array"))
                except json.JSONDecodeError:
                    raise ValidationError(_("Arguments must be valid JSON")) from None

    def action_get_prompt(self):
        """Open a wizard to get the prompt with parameters."""
        self.ensure_one()
        return {
            "name": _("Get Prompt: %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "mcp.prompt.get.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_prompt_id": self.id,
                "default_server_id": self.server_id.id,
            },
        }

    def get_prompt(self, arguments=None):
        """Get the prompt with the provided arguments.

        Args:
            arguments (dict, optional): The arguments to pass to the prompt

        Returns:
            dict: The prompt result
        """
        self.ensure_one()

        if self.server_id.state != "running":
            raise UserError(_("Server is not running"))

        # Use the server's async methods to communicate with the MCP server
        try:
            result = self.server_id._run_async_in_thread(
                self._async_get_prompt(arguments or {})
            )
            return result
        except Exception as e:
            _logger.exception(
                "Error getting prompt %(prompt_name)s: %(error)s",
                {"prompt_name": self.name, "error": str(e)},
            )
            raise UserError(
                _("Error getting prompt: %(error)s") % {"error": str(e)}
            ) from None

    async def _async_get_prompt(self, arguments):
        """Get a prompt from the MCP server using async API.

        Args:
            arguments: The arguments to pass to the prompt

        Returns:
            The prompt result
        """
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        # Parse command and arguments from the server
        command = self.server_id.command
        args = json.loads(self.server_id.args) if self.server_id.args else []
        env_vars = (
            json.loads(self.server_id.env_vars) if self.server_id.env_vars else None
        )

        # Log the command that will be executed
        _logger.info(
            "Getting prompt %s from MCP server with command: %s %s",
            self.name,
            command,
            " ".join(args),
        )

        # Create server parameters
        server_params = StdioServerParameters(command=command, args=args, env=env_vars)

        result = None

        # Connect to the server via stdio
        async with stdio_client(server_params) as (read, write):
            # Log successful connection
            _logger.info("Successfully established stdio connection to MCP server")

            async with ClientSession(read, write) as session:
                # Initialize the connection
                await session.initialize()
                _logger.info("Successfully initialized MCP session")

                # Get the prompt
                _logger.info(
                    "Getting prompt %s with arguments: %s", self.name, arguments
                )
                response = await session.get_prompt(self.name, arguments)

                # Process the response
                result = {"description": response.description, "messages": []}

                # Extract messages from the response
                for message in response.messages:
                    message_data = {"role": message.role, "content": []}

                    # Process content based on type
                    if hasattr(message, "content") and message.content:
                        for content_item in message.content:
                            if hasattr(content_item, "text"):
                                message_data["content"].append(
                                    {"type": "text", "text": content_item.text}
                                )
                            elif hasattr(content_item, "data"):
                                message_data["content"].append(
                                    {
                                        "type": content_item.type,
                                        "data": content_item.data,
                                        "mimeType": getattr(
                                            content_item, "mimeType", None
                                        ),
                                    }
                                )

                    result["messages"].append(message_data)

                _logger.info("Successfully got prompt %s", self.name)

        return result
