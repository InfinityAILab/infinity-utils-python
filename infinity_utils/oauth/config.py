from typing import Optional

from pydantic import BaseModel, Field


class OAuthConfig(BaseModel):
    """Configuration for OAuth client applications."""

    # OAuth Client Configuration
    client_id: str
    client_secret: str
    audience: str

    # IDP Configuration
    idp_jwt_issuer: str = Field(default="https://id-backend.infinitylab.ai")
    idp_jwt_token_url: str = Field(default="https://id-backend.infinitylab.ai/oauth/token")
    idp_jwks_url: str = Field(default="https://id-backend.infinitylab.ai/.well-known/jwks.json")
    idp_jwt_algorithm: str = Field(default="RS256")

    # JWT Configuration for Internal Tokens
    jwt_secret_key: str
    jwt_algorithm: str = Field(default="HS256")
    jwt_issuer: str
    jwt_access_token_expire_minutes: int = Field(default=30)

    # Database Configuration
    firestore_database_id: str
    google_cloud_project: str
    google_application_credentials: Optional[str] = None

    # User Data Configuration
    additional_user_fields: dict = Field(default_factory=dict)

    class Config:
        extra = "allow"
