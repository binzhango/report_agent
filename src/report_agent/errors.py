"""Errors whose messages are intentionally safe to show to users and models."""


class ReportError(ValueError):
    """Use only for application-authored guidance, never raw external exceptions."""

    def __init__(self, message: str, *, code: str = "invalid_request"):
        super().__init__(message)
        self.code = code
