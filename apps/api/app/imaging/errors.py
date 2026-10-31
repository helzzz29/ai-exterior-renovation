"""Errors raised by the imaging package."""


class ImageRejected(Exception):
    """Raised when an upload cannot be used at all. `code` + plain-language `message`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
