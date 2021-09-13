from re import U
import time
from typing import Dict, Optional

import jwt
import os

from app.helpers.settings import settings
from app.db import schema


def signJWT(user: schema.User) -> schema.Token:
    payload = {
        "jwt": "",
        "user_id": str(user.id),
        "expires": time.time() + 3600 * 24 * 365
    }
    token = jwt.encode(payload, settings.JWT_SECRET,
                       algorithm=settings.JWT_ALGORITHM)

    return schema.Token(token=token, user_id=user.id)


def signCSRF(user: schema.User) -> schema.Token:
    payload = {
        "csrf": "",
        "user_id": str(user.id),
        "expires": time.time() + 3600 * 24 * 365
    }
    token = jwt.encode(payload, settings.JWT_SECRET,
                       algorithm=settings.JWT_ALGORITHM)

    return schema.Token(token=token, user_id=user.id)


def decodeJWT(token: str) -> Optional[schema.Token]:
    try:
        decoded_token = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if decoded_token["expires"] <= time.time():
            return None

        return schema.Token(token=token, user_id=decoded_token['user_id'])
    except:
        return None
