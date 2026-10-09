"""Self-profile request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from src.profile import Profile


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    email: str | None = Field(default=None, max_length=254)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)


class ProfileResponse(BaseModel):
    id: int
    email: str
    first_name: str | None
    last_name: str | None
    role: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.isoformat()

    @classmethod
    def from_profile(cls, profile: Profile) -> "ProfileResponse":
        return cls(
            id=profile.id,
            email=profile.email,
            first_name=profile.first_name,
            last_name=profile.last_name,
            role=profile.role,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )
