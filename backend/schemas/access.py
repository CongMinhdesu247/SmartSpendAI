"""Data validation schemas for access."""

from pydantic import BaseModel, Field


class LoginInput(BaseModel):
    username: str = Field(default="chuso", max_length=32)
    password: str = Field(min_length=1, max_length=256)


class RegisterInput(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=12, max_length=128)
