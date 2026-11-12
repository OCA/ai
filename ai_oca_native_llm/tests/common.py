class OpenAIMockMessage:
    def __init__(self, content, tool_calls=None):
        self.message = type(
            "MockMsg",
            (),
            {"content": content, "tool_calls": tool_calls or []},
        )()


class OpenAIMockResponse:
    def __init__(self, message_content, tool_calls=None):
        self.choices = [OpenAIMockMessage(message_content, tool_calls=tool_calls)]
        self.usage = None


class OpenAIMockDecisionResponse:
    def __init__(self, answers=None):
        self.answers = answers or []
        self.model = "decision"
        self.usage = None
