"""
OAuth Authentication Module for FastAPI Applications

Provides reusable OAuth authentication components for FastAPI apps that integrate
with external OAuth providers and provide JWT token management.
"""

from .config import OAuthConfig
from .dependencies import create_auth_dependencies
from .oauth_service import OAuthClient
from .schemas import AuthorizeRequest, GrantType, Scope, TokenRequest
from .types import User

__all__ = [
    "OAuthClient",
    "OAuthConfig",
    "TokenRequest",
    "AuthorizeRequest",
    "GrantType",
    "Scope",
    "create_auth_dependencies",
    "User",
]
