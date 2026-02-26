class OllamaMockMessage:
    def __init__(self, content):
        self.content = content


class OllamaMockResponse:
    def __init__(self, message_content):
        self.message = OllamaMockMessage(message_content)
