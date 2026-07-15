"""Business exceptions for image recognition."""


class RecognitionError(Exception):
    """Base exception for recognition errors."""

    def __init__(self, message: str, code: int = -1) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ProviderNotFoundError(RecognitionError):
    """Raised when no provider supports the requested task type."""

    def __init__(self, message: str = "No provider available") -> None:
        super().__init__(message, code=404)


class ProviderUnavailableError(RecognitionError):
    """Raised when a provider is registered but its dependencies are missing."""

    def __init__(self, message: str = "Provider is unavailable") -> None:
        super().__init__(message, code=503)


class ImageDecodeError(RecognitionError):
    """Raised when an image cannot be decoded."""

    def __init__(self, message: str = "Failed to decode image") -> None:
        super().__init__(message, code=400)
