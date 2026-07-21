class SmsError(RuntimeError):
    def __init__(self, message_zh: str) -> None:
        super().__init__(message_zh)
        self.message_zh = message_zh
