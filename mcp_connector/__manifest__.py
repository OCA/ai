{
    "name": "MCP Connector",
    "summary": "Integrate Odoo with Model Context Protocol (MCP) servers",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "Escodoo,Odoo Community Association (OCA)",
    "maintainers": ["marcelsavegnago"],
    "website": "https://github.com/OCA/ai",
    "depends": ["base"],
    "external_dependencies": {
        "python": [
            "mcp",
            "uv",
        ]
    },
    "data": [
        "security/ir.model.access.csv",
        "views/mcp_server_views.xml",
        "views/mcp_tool_views.xml",
        "views/mcp_resource_views.xml",
        "views/mcp_prompt_views.xml",
        "views/menu_views.xml",
        "wizard/mcp_tool_call_wizard.xml",
        "wizard/mcp_resource_read_wizard.xml",
        "wizard/mcp_prompt_get_wizard.xml",
    ],
    "demo": [
        "demo/demo_data.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
