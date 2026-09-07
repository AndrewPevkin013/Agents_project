import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not value.replace("_","").replace("-","").isalnum():
            raise ValueError("Username may contain only letters, digits, '_' and '-'")
        return value

class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)

class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)

class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=20)

class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}

class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
