import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import OAuthConfig
from .jwt_helpers import JWTHelper
from .types import User

logger = logging.getLogger(__name__)


def create_auth_dependencies(config: OAuthConfig):
    """
    Factory function to create authentication dependencies for a specific OAuth configuration.

    Returns a tuple of (get_current_user, get_optional_user, CurrentUser, OptionalUser)
    """
    jwt_helper = JWTHelper(config)
    http_bearer = HTTPBearer(auto_error=False)

    async def get_current_user(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)],
    ) -> User:
        """Extract and validate JWT token from Authorization header."""
        if not credentials:
            logger.warning("No authorization credentials provided")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization header",
                headers={"WWW-Authenticate": f'Bearer realm="{config.audience}"'},
            )

        if not credentials.credentials:
            logger.warning("Empty authorization token provided")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Empty authorization token",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )

        try:
            # Verify JWT token with proper audience
            decoded_token = jwt_helper.verify_internal_jwt(credentials.credentials, audience=config.audience)

            # Log successful authentication (without sensitive data)
            logger.info(f"User authenticated successfully: {decoded_token.get('sub', 'unknown')}")

            # Create and return User object
            return User(**decoded_token)

        except HTTPException:
            # Re-raise HTTPExceptions from verify_jwt
            raise
        except ValueError as err:
            # Handle Pydantic validation errors when creating User object
            logger.error(f"User object validation failed: {err}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )
        except Exception as err:
            # Catch any other unexpected errors without leaking details
            logger.error(f"Unexpected authentication error: {type(err).__name__}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )

    async def get_optional_user(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)],
    ) -> User | None:
        """
        Optional authentication dependency that returns None if no valid token is provided.
        """
        if not credentials or not credentials.credentials:
            return None

        try:
            decoded_token = jwt_helper.verify_internal_jwt(credentials.credentials, audience=config.audience)
            logger.info(f"Optional user authenticated: {decoded_token.get('sub', 'unknown')}")
            return User(**decoded_token)
        except Exception:
            # For optional auth, we don't raise errors, just return None
            logger.debug("Optional authentication failed, returning None")
            return None

    # Type aliases for easier imports
    CurrentUser = Annotated[User, Depends(get_current_user)]
    OptionalUser = Annotated[User | None, Depends(get_optional_user)]

    return get_current_user, get_optional_user, CurrentUser, OptionalUser
