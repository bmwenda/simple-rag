"""Profile use cases shared by HTTP handlers and other adapters."""

from typing import Protocol

from .profile import Profile, normalize_changes


class ProfileRepository(Protocol):
    def get_owner(self) -> Profile | None: ...

    def update_profile(self, user_id: int, changes: dict[str, str | None]) -> Profile: ...

    def delete_profile(self, user_id: int) -> None: ...


class ManagedProfileRepository(ProfileRepository, Protocol):
    """A repository whose connection pool belongs to the app lifespan."""

    def close(self) -> None: ...


class ProfileService:
    def __init__(self, repository: ProfileRepository) -> None:
        self._repository = repository

    def get_owner(self) -> Profile | None:
        return self._repository.get_owner()

    def update_profile(self, user_id: int, changes: dict[str, str | None]) -> Profile:
        return self._repository.update_profile(user_id, normalize_changes(changes))

    def delete_profile(self, user_id: int) -> None:
        self._repository.delete_profile(user_id)
