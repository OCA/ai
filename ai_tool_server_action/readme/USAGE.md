1. For Server Actions containing **Python code**, you have access to the arguments sent by the AI in `env.context.get('tool_args')`. To return a result, simply assign a dictionary to the local `action` variable:

    ```python
    args = env.context.get('tool_args', {})
    search_term = args.get('query')
    records = env['res.partner'].search([('name', 'ilike', search_term)], limit=5)
    action = {'results': records.mapped('display_name')}
    ```

2. **Standard Server Actions** (e.g. Update Record, Create Activity, Send Email) work out-of-the-box. When they successfully execute, the AI will automatically receive a `{"status": "success"}` response. Any User Interface actions (like opening a wizard or window) are silently intercepted to prevent confusing the AI.

3. **External / MCP Usage:** When the AI invokes these tools externally (via the MCP protocol or general chat) it won't have an active Odoo record context.
   - For Standard Actions to work in this scenario, simply declare an `active_id` parameter in your **Input Schema** and the module will intelligently inject it into the execution context for you.
   - The wizard pre-loads these intelligent default schemas automatically for you based on the action type.
