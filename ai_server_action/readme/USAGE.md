This module adds a new server action type: **AI OCA Action**.

To use it:
1. Go to `Settings > Technical > Actions > Server Actions`
2. Create a new action and select **AI OCA Action** as the state
3. Select an AI Connection (Ollama)
4. Define the prompt — supports dynamic placeholders using Qweb syntax (e.g. `{{ object.name }}`)
5. Optionally select tools the AI can call during execution
6. Define what to do with the result:
   - **Post Message**: posts the AI response as a chatter message on the record
   - **Update Record**: writes the AI response to a specific field

To extend with a new AI provider, inherit `ai.connection` and add a new selection 
value to `kind`, then implement the corresponding `_run_{kind}` method.