import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from jwt import InvalidTokenError
from starlette import status

from db import SessionDep
from model import User, get_user
from security.oauth import oauth2_scheme, ALGORITHM, SECRET_KEY, TokenData

BearerTokenDep = Annotated[str, Depends(oauth2_scheme)]


async def get_current_user(token: BearerTokenDep, session: SessionDep):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise credentials_exception

    user = get_user(session, user_id=uuid.UUID(token_data.username))

    if user is None:
        raise credentials_exception
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
