"""Profile rules shared by the HTTP API and persistence layer."""

import re
from dataclasses import dataclass
from datetime import datetime

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(frozen=True)
class Profile:
    id: int
    email: str
    first_name: str | None
    last_name: str | None
    role: str
    created_at: datetime
    updated_at: datetime


class DuplicateEmailError(Exception):
    """The requested email is already assigned to another user."""

    def __init__(self, message: str = "Email is already in use") -> None:
        super().__init__(message)


class ProfileNotFoundError(Exception):
    """The user was deleted or does not exist."""


class InvalidProfileError(Exception):
    """A profile update violates the public request contract."""


def normalize_email(value: str) -> str:
    email = value.strip().casefold()
    if not _EMAIL_PATTERN.fullmatch(email):
        raise InvalidProfileError("Enter a valid email address")
    return email


def normalize_changes(changes: dict[str, str | None]) -> dict[str, str | None]:
    if not changes:
        raise InvalidProfileError("Provide at least one profile field")
    if set(changes) - {"email", "first_name", "last_name"}:
        raise InvalidProfileError("Unknown profile field")
    normalized = dict(changes)
    if "email" in normalized:
        email = normalized["email"]
        if email is None:
            raise InvalidProfileError("Email is required")
        normalized["email"] = normalize_email(email)
    for name in ("first_name", "last_name"):
        if name in normalized and normalized[name] is not None:
            value = normalized[name]
            assert value is not None
            normalized[name] = value.strip() or None
    return normalized
