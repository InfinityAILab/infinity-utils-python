from typing import Optional

from pydantic import BaseModel


class User(BaseModel):
    """User model for authenticated users."""

    sub: str
    email: Optional[str] = None
    name: Optional[str] = None
    role: str = "user"
    iat: Optional[int] = None
    exp: Optional[int] = None
    iss: Optional[str] = None
    aud: Optional[str] = None

    class Config:
        extra = "allow"
