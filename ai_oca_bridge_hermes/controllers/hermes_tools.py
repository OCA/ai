# Copyright 2026-TODAY Akretion - Raphael Valyi <raphael.valyi@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Soft dependency on ai_tool
try:
    from odoo.addons.ai_tool.tools import aitool

    AI_TOOL_AVAILABLE = True
except ImportError:
    aitool = None  # noqa: F841
    AI_TOOL_AVAILABLE = False


class HermesToolsController(http.Controller):
    """Endpoint for Hermes to execute Odoo tools.

    This controller provides a native API for Hermes to call Odoo tools.
    If ai_tool is installed, tools are also available via MCP.

    Tools are discovered dynamically from:
    1. ai.tool records (when ai_tool is installed)
    2. hermes.tools.mock methods (always available for testing)
    """

    @http.route(
        "/hermes/tools/execute",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def hermes_tools_execute(self, **kwargs):
        """Execute an Odoo tool and return the result.

        Expected JSON body:
        {
            "tool": "hello_world",
            "args": {"name": "Raphaël"}
        }
        """
        # Validate auth token from Authorization header
        auth_header = request.httprequest.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip() if auth_header else ""

        gateway = (
            request.env["hermes.gateway"]
            .sudo()
            .search([("webhook_token", "=", token), ("active", "=", True)], limit=1)
        )
        if not gateway:
            return {"status": "error", "message": "Invalid token"}

        data = request.get_json_data()
        if not data:
            return {"status": "error", "message": "No JSON data"}

        tool_name = data.get("tool")
        args = data.get("args", {})

        if not tool_name:
            return {"status": "error", "message": "Missing 'tool' parameter"}

        # Get the AI user from the gateway for permission context
        ai_user = gateway.ai_user_id
        if not ai_user:
            return {"status": "error", "message": "No AI user configured"}

        # Execute tool with the AI user's permissions
        try:
            result = self._execute_tool(request.env(user=ai_user.id), tool_name, args)
            return {"status": "ok", "result": result}
        except Exception as e:
            _logger.warning("Hermes tool execution failed: %s - %s", tool_name, e)
            return {"status": "error", "message": str(e)}

    @http.route(
        "/hermes/tools/list",
        type="json",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
    )
    def hermes_tools_list(self, **kwargs):
        """List available tools with their schemas."""
        auth_header = request.httprequest.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip() if auth_header else ""

        gateway = (
            request.env["hermes.gateway"]
            .sudo()
            .search([("webhook_token", "=", token), ("active", "=", True)], limit=1)
        )
        if not gateway:
            return {"tools": [], "error": "Invalid token"}

        tools = self._get_available_tools(request.env)
        return {"tools": tools}

    def _get_available_tools(self, env):
        """Return list of available tool definitions.

        Discovers tools from:
        1. ai.tool records (if ai_tool installed)
        2. hermes.tools.mock methods (always available)
        """
        tools = []

        # 1. ai.tool records (when ai_tool is installed)
        if AI_TOOL_AVAILABLE and hasattr(env, "ai.tool"):
            try:
                ai_tools = env["ai.tool"].search([])
                for tool in ai_tools:
                    try:
                        definition = tool._get_tool_definition()
                        tools.append(
                            {
                                "name": definition.get("name", tool.name),
                                "description": tool.description or "",
                                "input_schema": definition.get("inputSchema", {}),
                                "output_schema": definition.get("outputSchema", {}),
                                "source": "ai.tool",
                            }
                        )
                    except Exception as e:
                        _logger.debug("Skipping ai.tool %s: %s", tool.name, e)
            except Exception as e:
                _logger.debug("Could not load ai.tool records: %s", e)

        # 2. Mock tools (always available for testing)
        mock_model = env.get("hermes.tools.mock")
        if mock_model:
            for method_name in dir(mock_model):
                if not method_name.startswith("_ai_"):
                    continue
                method = getattr(mock_model, method_name)
                if not callable(method):
                    continue

                # Build simple schema from docstring/defaults
                doc = (method.__doc__ or "").strip().split("\n")[0]
                tools.append(
                    {
                        "name": method_name[4:],  # Remove _ai_ prefix
                        "description": doc,
                        "input_schema": {"type": "object", "properties": {}},
                        "output_schema": {"type": "object", "properties": {}},
                        "source": "hermes.tools.mock",
                    }
                )

        return tools

    def _execute_tool(self, env, tool_name, args):
        """Execute a tool by name with the given environment."""
        # Try ai.tool first (if ai_tool is installed)
        if AI_TOOL_AVAILABLE:
            try:
                ai_tool = env["ai.tool"].search([("name", "=", tool_name)], limit=1)
                if ai_tool:
                    return ai_tool._execute_tool(**args)
            except Exception as e:
                _logger.debug("ai.tool execution failed: %s", e)

        # Fallback to mock tools
        method_name = f"_ai_{tool_name}"
        mock_model = env.get("hermes.tools.mock")
        if mock_model and hasattr(mock_model, method_name):
            method = getattr(mock_model, method_name)
            return method(**args)

        raise ValueError(f"Unknown tool: {tool_name}")
