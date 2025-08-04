from enum import StrEnum

from pydantic import BaseModel


class AuthorizeRequest(BaseModel):
    client_id: str
    redirect_uri: str
    code_challenge: str
    state: str


class GrantType(StrEnum):
    AUTHORIZATION_CODE = "authorization_code"


class Scope(StrEnum):
    OPENID = "openid"
    PROFILE = "profile"
    EMAIL = "email"


class TokenRequest(BaseModel):
    code: str
    code_verifier: str
    client_id: str
    redirect_uri: str
    grant_type: GrantType = GrantType.AUTHORIZATION_CODE
