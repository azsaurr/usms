"""
USMS Errors Module.

This module defines custom exception classes for the USMS application.
These exceptions provide more meaningful error handling and debugging
by categorizing different failure scenarios.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


class USMSMeterNumberError(Exception):
    """Exception raised for when invalid meter number is given."""

    def __init__(self, meter_no: str | int = "is") -> None:
        """Initialize the exception."""
        self.message = f"Meter {meter_no} not found."
        super().__init__(self.message)


class USMSLoginError(Exception):
    """Exception raised for when unable to login."""

    def __init__(self, message: str = "Invalid login.") -> None:
        """Initialize the exception."""
        self.message = message
        super().__init__(self.message)


class USMSPageResponseError(Exception):
    """Exception raised for when error during page retrieval."""

    def __init__(self, page_url: str = "USMS page") -> None:
        """Initialize the exception."""
        self.message = f"Response from {page_url} was not expected."
        super().__init__(self.message)


class USMSFutureDateError(Exception):
    """Exception raised for when future date is given."""

    def __init__(self, given_date: "datetime" = "Given date") -> None:
        """Initialize the exception."""
        self.message = f"{given_date} is in the future."
        super().__init__(self.message)


class USMSConsumptionHistoryNotFoundError(Exception):
    """Exception raised for when no consumption history can be retrieved."""

    def __init__(self, message: str = "Consumption history not found.") -> None:
        """Initialize the exception."""
        self.message = message
        super().__init__(self.message)


class USMSInvalidParameterError(Exception):
    """Exception raised for when an invalid parameter is passed."""

    def __init__(self, given: str, expected: str | list) -> None:
        """Initialize the exception."""
        self.message = f"Given {given}, expected {expected}."
        super().__init__(self.message)


class USMSNotInitializedError(Exception):
    """Exception raised for when an operation is attempted on an unitialized object."""

    def __init__(self, class_name: str) -> None:
        """Initialize the exception."""
        self.message = f"{class_name} must be initialized first."
        super().__init__(self.message)
