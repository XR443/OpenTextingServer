import uuid
from datetime import datetime, timezone, timedelta

import jwt
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from pydantic import BaseModel
from sqlmodel import Field, Session

from model import User, get_user

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# to get a string like this run:
# openssl rand -hex 32
# todo move to env
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

password_hash = PasswordHash.recommended()
# todo
dummy_password = "dummypassword"
DUMMY_HASH = password_hash.hash(dummy_password)


class AccessToken(BaseModel):
    token: str = Field(primary_key=True)
    type: str = Field()


class RefreshToken(BaseModel):
    token: str = Field(primary_key=True)
    type: str = Field()


class TokenData(BaseModel):
    username: str | None = None


def hash_password(user: User, password: str) -> str:
    return password_hash.hash(password)


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    user = get_user(session, username)

    # todo remove
    if not user:
        user = User(id=uuid.uuid4(), username=username, password=password_hash.hash(password), host="localhost")
        session.add(user)
        session.commit()

    if not user or not user.password:
        password_hash.verify(password or reversed(dummy_password), DUMMY_HASH)
        return None
    if not password_hash.verify(password, user.password):
        return None
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    # todo
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
