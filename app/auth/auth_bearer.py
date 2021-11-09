# based on
# https://dev.to/carminezacc/securely-storing-jwts-in-flutter-web-apps-2nal
# https://testdriven.io/blog/fastapi-jwt-auth/

from typing import Optional, cast
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.security.utils import get_authorization_scheme_param

from app.db import schema

from app.auth.auth_handler import decodeJWT


def get_cookies(request: Request):
    cookie_authorization: Optional[str] = request.cookies.get("authorization")
    if cookie_authorization == None:
        raise HTTPException(status_code=403, detail="Invalid authorization code.")

    csrf_scheme, csrf_token = get_authorization_scheme_param(
        cast(str, cookie_authorization)
    )
    return csrf_scheme, csrf_token


class JWTBearer(HTTPBearer):
    def __init__(self, auto_error: bool = True):
        super(JWTBearer, self).__init__(auto_error=auto_error)

    async def __call__(self, request: Request):
        credentials: Optional[HTTPAuthorizationCredentials] = await super(
            JWTBearer, self
        ).__call__(request)
        if credentials == None:
            raise HTTPException(status_code=403, detail="Invalid authorization code.")
        else:
            credentials = cast(HTTPAuthorizationCredentials, credentials)

        jwt_token = credentials.credentials

        if jwt_token == None:
            raise HTTPException(status_code=403, detail="Invalid authorization code.")

        jwt_payload: schema.Token = decodeJWT(jwt_token)

        return schema.Token(token=jwt_token, user_id=jwt_payload.user_id)


class OptionalJWTBearer(JWTBearer):
    def __init__(self, auto_error: bool = True):
        super(JWTBearer, self).__init__(auto_error=auto_error)

    async def __call__(self, request: Request):
        try:
            return await super().__call__(request=request)
        except:
            return None
