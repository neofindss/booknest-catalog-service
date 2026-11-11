class AppError(Exception):
    """A domain or application failure with an HTTP status and a stable error code."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class DuplicateISBN(Exception):
    """Raised when a book is inserted with an ISBN that is already stored."""


class DuplicateReservation(Exception):
    """Raised when a reservation for the same order id already exists."""
