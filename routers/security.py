import uuid
from datetime import timedelta
from typing import Annotated, List, Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Header

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import and_
from sqlmodel import select
from starlette import status
from starlette.responses import StreamingResponse

from db import SessionDep
from model import User, UserInfo
from model.user import map_user_to_info, get_user
from security import authenticate_user, AccessToken, ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token, CurrentUserDep, \
    Key
from security.key import KeyWithUserInfo
from security.oauth import hash_password

router = APIRouter(
    tags=["security"],
    responses={404: {"description": "Not found"}},
)


class LoginData(BaseModel):
    username: str
    password: str
    # public_key: bytes | None


# todo в другое место
@router.get("/info/about/me", response_model=UserInfo)
async def user_info(current_user: CurrentUserDep):
    return map_user_to_info(current_user)


# todo в другое место
@router.get("/info/about/{user_id}", response_model=UserInfo)
async def user_info(user_id: uuid.UUID, current_user: CurrentUserDep, session: SessionDep):
    user = session.exec(select(User).where(User.id == user_id)).one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return map_user_to_info(user)


@router.get("/all", response_model=List[UserInfo])
async def all_users(session: SessionDep):
    return session.exec(select(User).order_by(User.username)).all()


@router.post("/token", response_model=AccessToken)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep):
    # async def login(form_data: Annotated[LoginData, Depends()], session: SessionDep):
    user: User = authenticate_user(session, form_data.username, form_data.password)

    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect username or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        # todo because user.id uuid
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )

    token = AccessToken(token=access_token, type="bearer")
    # todo
    # session.add(token)
    # session.commit()

    return token


@router.post("/keys/upload", response_model=KeyWithUserInfo)
async def upload_public_key(
        request: Request,
        session: SessionDep,
        current_user: CurrentUserDep,
):
    """
    Загрузка публичного ключа текущего пользователя
    """
    public_key = await request.body()
    # Проверяем, существует ли уже ключ у пользователя
    existing_key = session.exec(
        select(Key).where(Key.user == current_user.id)
    ).first()

    if existing_key:
        # Обновляем существующий ключ
        existing_key.public_key = public_key
        session.add(existing_key)
    else:
        # Создаем новый ключ
        new_key = Key(
            user=current_user.id,
            public_key=public_key
        )
        session.add(new_key)

    session.commit()

    # Получаем обновленный ключ с информацией о пользователе
    key = session.exec(
        select(Key).where(Key.user == current_user.id)
    ).first()

    return KeyWithUserInfo(
        user_id=current_user.id,
        username=current_user.username
    )


class SearchKeysRequest(BaseModel):
    """DTO для поиска ключей по username"""
    username: str = Field(
        min_length=1,
        max_length=50,
        description="Username для поиска (частичное совпадение)"
    )


@router.get("/keys/search", response_model=list[KeyWithUserInfo])
async def search_public_keys(
        user_request: SearchKeysRequest,
        session: SessionDep,
        current_user: CurrentUserDep,
):
    """
    Поиск публичных ключей по username (частичное совпадение)
    """
    # Ищем пользователей с частичным совпадением username
    users = session.exec(
        select(User).where(
            and_(User.username.contains(user_request.username), User.id != current_user.id),
        )
    ).all()

    if not users:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No users found with this username"
        )

    # Получаем ключи для найденных пользователей
    result = []
    for user in users:
        key = session.exec(
            select(Key).where(Key.user == user.id)
        ).first()

        if key:
            result.append(
                KeyWithUserInfo(
                    user_id=user.id,
                    username=user.username
                )
            )

    return result


@router.get("/keys/{user_id}", response_model=KeyWithUserInfo)
async def get_public_key_by_user_id(
        user_id: uuid.UUID,
        session: SessionDep,
        current_user: CurrentUserDep,
):
    """
    Получение публичного ключа по ID пользователя
    """
    # Проверяем существование пользователя
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Получаем ключ пользователя
    key = session.exec(
        select(Key).where(Key.user == user_id)
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found"
        )

    def byte_data():
        yield key.public_key

    return StreamingResponse(
        byte_data(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename=messages.bin",
            "X-Content-Type-Options": "nosniff",
        }
    )


@router.delete("/keys", response_model=dict)
async def delete_public_key(
        session: SessionDep,
        current_user: CurrentUserDep,
):
    """
    Удаление публичного ключа пользователя
    """
    # Находим и удаляем ключ
    key = session.exec(
        select(Key).where(Key.user == current_user.id)
    ).first()

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Public key not found for this user"
        )

    session.delete(key)
    session.commit()

    return {
        "message": "Public key deleted successfully",
        "user_id": str(current_user.id)
    }
