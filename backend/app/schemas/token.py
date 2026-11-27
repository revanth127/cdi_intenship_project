from typing import Optional
from pydantic import BaseModel
from app.schemas.user import UserResponse


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    user: Optional[UserResponse] = None


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    role: Optional[str] = None
    type: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class DemoLoginCredential(BaseModel):
    title: str
    email: str
    password: str
    access: str
