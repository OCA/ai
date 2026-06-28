## Why This Module?

The AI revolution is changing how users interact with software. Odoo users should be able to ask questions, get help, and automate tasks using natural language - directly inside the interface they already use daily.

## Architecture Rationale

### Queue-Based Design (Not Real-Time)
We chose polling over WebSockets for maximum compatibility:
- Works behind firewalls and proxies
- No WebSocket server needed
- Simple to debug and monitor
- Compatible with all Odoo deployments

### Standalone Gateway Script
The `scripts/hermes_odoo_gateway.py` script runs outside Odoo:
- No need to install Hermes inside Odoo's Python environment
- AI processing happens in a separate process
- Can be restarted independently
- Supports multiple Odoo instances

### Extension Points
The module is intentionally minimal. Extra features are added via child modules:
- `ai_oca_bridge_hermes_support` - Support ticket escalation for instance
- Custom handlers via the gateway script's handler system

### Escalation Concept
The module includes a minimal escalation hook (`_action_escalate`) so the AI can signal when human intervention is needed. The base module does not implement any specific escalation backend — child modules can override this hook to create tickets, notify teams, or route to another Hermes instance.

## Security Model

- Webhook tokens are auto-generated and stored securely
- AI users are regular Odoo users with limited permissions
- Gateway script runs with its own credentials
- No direct database access from the gateway

## Multi-Tenancy

A single Hermes instance can serve multiple Odoo databases:
- Each database has its own gateway configuration
- Session keys include database hash for isolation
- Messages are queued per-gateway

## MCP Compatibility

This module is compatible with the `ai_oca_mcp` module (Model Context Protocol). If `ai_oca_mcp` is installed, tools defined via `ai.tool` are automatically exposed through the MCP endpoint. The Hermes gateway can then call Odoo tools either via our native API or through MCP — both approaches work side by side.

## Future Directions

- Native Hermes gateway adapter (inside Hermes process)
- WebSocket support for real-time communication
- Voice/video integration
- Multi-modal AI (images, documents)
