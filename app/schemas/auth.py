"""Authentication request and response schemas."""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field("", max_length=200)
    role: Literal["owner", "admin", "agent", "employee"] = "agent"
    tenant_slug: str | None = Field(None, min_length=1, max_length=50)
    tenant_name: str | None = Field(None, min_length=1, max_length=200)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(ch.isalpha() for ch in value) or not any(ch.isdigit() for ch in value):
            raise ValueError("password must contain at least one letter and one digit")
        return value

    @model_validator(mode="after")
    def validate_role_fields(self):
        if self.role == "owner":
            if not self.tenant_slug:
                raise ValueError("owner registration requires tenant_slug")
            if not self.tenant_name:
                raise ValueError("owner registration requires tenant_name")
        elif not self.tenant_slug:
            raise ValueError("non-owner registration requires tenant_slug")
        return self


class LoginRequest(BaseModel):
    tenant_slug: str = Field(..., min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    tenant_id: str
    tenant_slug: str
    email: EmailStr
    display_name: str
    role: Literal["owner", "admin", "agent", "employee"]
    is_active: bool

    model_config = {"from_attributes": True}


class AuthResponse(TokenResponse):
    user: UserResponse
