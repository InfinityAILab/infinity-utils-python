import logging
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException
from google.cloud import firestore

from .config import OAuthConfig
from .jwt_helpers import JWTHelper
from .schemas import TokenRequest

logger = logging.getLogger(__name__)


class OAuthClient:
    """OAuth client service for handling authentication flows."""

    def __init__(self, config: OAuthConfig):
        self.config = config
        self.jwt_helper = JWTHelper(config)
        self.router = APIRouter(prefix="/oauth")
        self._setup_routes()

    def _setup_routes(self):
        """Setup OAuth routes."""

        @self.router.post("/token")
        async def oauth_token(request: TokenRequest):
            return await self._handle_token_exchange(request)

    def get_firestore_client(self):
        """Get Firestore client instance."""
        return firestore.Client(database=self.config.firestore_database_id, project=self.config.google_cloud_project)

    async def _handle_token_exchange(self, request: TokenRequest) -> Dict[str, Any]:
        """Handle OAuth token exchange."""

        # Validate client_id
        if request.client_id != self.config.client_id:
            raise HTTPException(status_code=400, detail="Invalid client_id")

        # Exchange code for tokens with external OAuth provider
        tokens = await self._exchange_code_for_tokens(request)

        # Verify the external ID token
        user_info = await self._verify_external_token(tokens)

        # Save or update user in Firestore
        await self._save_user_to_firestore(user_info)

        # Generate internal JWT token
        jwt_token = self._generate_internal_token(user_info)

        return {
            "access_token": jwt_token,
            "token_type": "Bearer",
            "expires_in": self.config.jwt_access_token_expire_minutes * 60,
        }

    async def _exchange_code_for_tokens(self, request: TokenRequest) -> Dict[str, Any]:
        """Exchange authorization code for tokens with external OAuth provider."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.config.idp_jwt_token_url,
                    json={
                        "code": request.code,
                        "code_verifier": request.code_verifier,
                        "client_id": request.client_id,
                        "client_secret": self.config.client_secret,
                        "redirect_uri": request.redirect_uri,
                        "grant_type": request.grant_type,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    timeout=30,
                )
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException:
                logger.error("OAuth token exchange timed out")
                raise HTTPException(status_code=408, detail="Token exchange timed out")
            except httpx.HTTPStatusError as e:
                logger.error(f"OAuth token exchange failed: {e.response.status_code}, {e.response.text}")
                raise HTTPException(status_code=400, detail="Failed to exchange code")
            except httpx.HTTPError as e:
                logger.error(f"OAuth token exchange network error: {e}")
                raise HTTPException(status_code=503, detail="OAuth service unavailable")

    async def _verify_external_token(self, tokens: Dict[str, Any]) -> Dict[str, Any]:
        """Verify the external ID token using JWKS."""
        if "id_token" not in tokens:
            logger.error("No id_token in OAuth response")
            raise HTTPException(status_code=400, detail="Invalid token response")

        try:
            user_info = self.jwt_helper.verify_idp_jwt(token=tokens["id_token"], audience=self.config.client_id)
            logger.info(f"Successfully verified external token for user: {user_info.get('sub')}")

            # Validate required user information
            if not user_info.get("sub"):
                logger.error("Missing 'sub' claim in external token")
                raise HTTPException(status_code=400, detail="Invalid token: missing subject")

            return user_info

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during external token verification: {e}")
            raise HTTPException(status_code=401, detail="External token verification failed")

    async def _save_user_to_firestore(self, user_info: Dict[str, Any]) -> None:
        """Save or update user information in Firestore."""
        try:
            db = self.get_firestore_client()
            users_collection = db.collection("users")
        except Exception as e:
            logger.error(f"Failed to initialize Firestore: {e}")
            raise HTTPException(status_code=503, detail="Database service unavailable")

        local_user_id = user_info["sub"]
        user_ref = users_collection.document(local_user_id)

        # Prepare user data
        user_data = {
            "sub": user_info["sub"],
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "last_login": firestore.SERVER_TIMESTAMP,
        }

        # Add any additional user fields configured for this client
        user_data.update(self.config.additional_user_fields)

        # Remove None values
        user_data = {k: v for k, v in user_data.items() if v is not None}

        try:
            user_doc = user_ref.get()
            if user_doc.exists:
                user_ref.update(user_data)
                logger.info(f"Updated existing user: {local_user_id}")
            else:
                user_ref.set(user_data)
                logger.info(f"Created new user: {local_user_id}")
        except Exception as e:
            logger.error(f"Failed to save user to Firestore: {e}")
            raise HTTPException(status_code=503, detail="Failed to save user data")

    def _generate_internal_token(self, user_info: Dict[str, Any]) -> str:
        """Generate internal JWT token for the authenticated user."""
        try:
            return self.jwt_helper.generate_jwt(
                payload={
                    "sub": user_info["sub"],
                    "name": user_info.get("name"),
                    "email": user_info.get("email"),
                    "role": "user",
                },
                audience=self.config.audience,
            )
        except Exception as e:
            logger.error(f"Failed to generate JWT: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate access token")
