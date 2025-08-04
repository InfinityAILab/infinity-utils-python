import copy
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Union, cast

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from fastapi.exceptions import HTTPException
from jwt.algorithms import RSAAlgorithm

from .config import OAuthConfig

logger = logging.getLogger(__name__)


class JWTHelper:
    """Helper class for JWT operations with OAuth configuration."""

    def __init__(self, config: OAuthConfig):
        self.config = config
        self._jwks_cache = None

    @lru_cache(maxsize=1)
    def get_jwks(self) -> dict[str, Any]:
        """Fetch and cache the JWKS from the IDP."""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(self.config.idp_jwks_url)
                response.raise_for_status()
                jwks = response.json()

                if "keys" not in jwks or not isinstance(jwks["keys"], list):
                    raise ValueError("Invalid JWKS structure")

                logger.info(f"Successfully fetched JWKS with {len(jwks['keys'])} keys")
                return jwks

        except httpx.TimeoutException:
            logger.error("JWKS fetch timed out")
            raise HTTPException(status_code=503, detail="JWKS service timeout")
        except httpx.HTTPStatusError as e:
            logger.error(f"JWKS fetch failed: {e.response.status_code}")
            raise HTTPException(status_code=503, detail="JWKS service unavailable")
        except (httpx.HTTPError, ValueError) as e:
            logger.error(f"JWKS fetch error: {e}")
            raise HTTPException(status_code=503, detail="JWKS service error")

    def get_signing_key(self, token: str) -> RSAPublicKey:
        """Get the signing key from JWKS for the given token."""
        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            if not kid:
                raise HTTPException(status_code=401, detail="Token missing key ID")

            jwks = self.get_jwks()

            signing_key = None
            for key in jwks["keys"]:
                if key.get("kid") == kid:
                    signing_key = key
                    break

            if not signing_key:
                logger.error(f"No matching key found for kid: {kid}")
                raise HTTPException(status_code=401, detail="Invalid token key")

            return cast(RSAPublicKey, RSAAlgorithm.from_jwk(signing_key))

        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token format")
        except Exception as e:
            logger.error(f"Error getting signing key: {e}")
            raise HTTPException(status_code=401, detail="Token verification failed")

    def generate_jwt(self, payload: dict, audience: str) -> str:
        """Generate a JWT token with the given payload."""
        token_payload = copy.deepcopy(payload)

        now = datetime.now(timezone.utc)
        ttl_seconds = self.config.jwt_access_token_expire_minutes * 60

        token_payload.update(
            {
                "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
                "iat": int(now.timestamp()),
                "iss": self.config.jwt_issuer,
                "aud": audience,
            }
        )

        return jwt.encode(token_payload, self.config.jwt_secret_key, algorithm=self.config.jwt_algorithm)

    def verify_jwt(
        self,
        token: str,
        key: Union[str, RSAPublicKey],
        algorithms: list[str],
        audience: str,
        issuer: str,
        leeway: Union[float, timedelta],
    ) -> dict[str, Any]:
        """Verify a JWT token and return its payload."""
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=algorithms,
                audience=audience,
                issuer=issuer,
                verify_signature=True,
                leeway=leeway,
                options={
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "require": ["exp", "iat", "iss", "aud", "sub"],
                },
            )
            return payload
        except jwt.ExpiredSignatureError as e:
            logger.error(f"Token expired: {e}")
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidAudienceError as e:
            logger.error(f"Invalid token audience: {e}")
            raise HTTPException(status_code=401, detail="Invalid token audience")
        except jwt.InvalidIssuerError:
            logger.error("Invalid token issuer")
            raise HTTPException(status_code=401, detail="Invalid token issuer")
        except jwt.InvalidSignatureError:
            logger.error("Invalid token signature")
            raise HTTPException(status_code=401, detail="Invalid token signature")
        except jwt.MissingRequiredClaimError as e:
            logger.error(f"Missing required claim: {e}")
            raise HTTPException(status_code=401, detail=f"Missing required claim: {e}")
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid token: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")
        except Exception as e:
            logger.error(f"Verification of JWT failed: {e}")
            raise HTTPException(status_code=401, detail="Authentication failed")

    def verify_idp_jwt(self, token: str, audience: str) -> dict[str, Any]:
        """Verify a JWT token issued by the IDP using JWKS."""
        signing_key = self.get_signing_key(token)

        payload = self.verify_jwt(
            token,
            signing_key,
            [self.config.idp_jwt_algorithm],
            audience,
            self.config.idp_jwt_issuer,
            timedelta(seconds=300),
        )
        return payload

    def verify_internal_jwt(self, token: str, audience: str) -> dict[str, Any]:
        """Verify a JWT token issued internally."""
        payload = self.verify_jwt(
            token,
            self.config.jwt_secret_key,
            [self.config.jwt_algorithm],
            audience,
            self.config.jwt_issuer,
            timedelta(seconds=300),
        )
        return payload
