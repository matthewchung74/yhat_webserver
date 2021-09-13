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

        # csrf_scheme, csrf_token = get_cookies(request)

        credentials: Optional[HTTPAuthorizationCredentials] = await super(
            JWTBearer, self
        ).__call__(request)
        if credentials == None:
            raise HTTPException(status_code=403, detail="Invalid authorization code.")
        else:
            credentials = cast(HTTPAuthorizationCredentials, credentials)

        jwt_scheme = credentials.scheme
        jwt_token = credentials.credentials

        # if csrf_token == None:
        #     raise HTTPException(status_code=403, detail="Invalid authorization code.")

        if jwt_token == None:
            raise HTTPException(status_code=403, detail="Invalid authorization code.")

        # if csrf_scheme != jwt_scheme or jwt_scheme == None:
        #     raise HTTPException(status_code=403, detail="Invalid authorization code.")

        jwt_payload: schema.Token = decodeJWT(jwt_token)
        # csrf_payload: schema.Token = decodeJWT(csrf_token)

        # if jwt_payload.user_id != csrf_payload.user_id:
        #     raise HTTPException(status_code=403, detail="Invalid authorization code.")

        return schema.Token(token=jwt_token, user_id=jwt_payload.user_id)
