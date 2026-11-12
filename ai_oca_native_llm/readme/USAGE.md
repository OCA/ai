Any Odoo model inheriting from `ai.llm.client` can invoke both System 1 Decision calls and System 2 Generative Chat calls:

```python
# 1. System 1 Decision Choice (single-pass tool/action selection)
choice_answer = self.decide_choice(
    input_data=[{"role": "user", "content": "What is today's date?"}],
    choices=[
        {"value": "get_date", "description": "Return today's current date"},
        {"value": "done", "description": "Respond directly without calling a tool"},
    ],
    instructions="Select the best action to advance the user request.",
)
# -> {'name': 'next_action', 'type': 'choice', 'choice': 'get_date', 'confidence': 0.98, 'probabilities': [...]}

# 2. System 2 Generative Chat Completion
reply = self.chat(
    messages=[{"role": "user", "content": "Hello!"}],
    model_type="fast",
)
```
