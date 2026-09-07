import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from jwt import InvalidTokenError
from starlette import status

from db import SessionDep
from model import User, get_user
from model.connections import ConnectionManager
from security.oauth import oauth2_scheme, ALGORITHM, SECRET_KEY, TokenData

connection_manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    return connection_manager


ConnectionManagerDep = Annotated[ConnectionManager, Depends(get_connection_manager)]
