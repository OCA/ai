class OpenAIMockMessage:
    def __init__(self, content):
        self.message = type("MockMsg", (), {"content": content})()


class OpenAIMockResponse:
    def __init__(self, message_content):
        self.choices = [OpenAIMockMessage(message_content)]
        self.usage = None
