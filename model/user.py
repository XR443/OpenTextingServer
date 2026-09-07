import uuid
from typing import List

from fastapi import HTTPException
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import Column, JSON
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.sql.operators import is_not
from sqlmodel import Field, SQLModel, select, Relationship


class UserBase(SQLModel):
    id: uuid.UUID = Field(primary_key=True)

    username: str = Field(index=True, unique_items=True)
    info: dict | None = Field(default=None, sa_column=Column(JSON))  # todo ограничить размер при сохранении


class User(UserBase, table=True):
    host: str | None = Field()  # todo Дополнительная таблица с набором хостов

    password: str | None = Field()

    outbox: list["Message"] = Relationship(back_populates="author",
                                           sa_relationship_kwargs={"foreign_keys": "Message.author_id"})
    inbox: list["Message"] = Relationship(back_populates="recipient",
                                          sa_relationship_kwargs={"foreign_keys": "Message.recipient_id"})


class UserInfo(UserBase):
    model_config = ConfigDict(alias_generator=to_camel,validate_by_name=True)
    id: uuid.UUID

    username: str
    info: dict | None = Field(default=None, sa_column=Column(JSON))


def get_user(session, username: str = None, user_id: uuid.UUID = None) -> User | None:
    if not username and not user_id:
        return None
    if user_id:
        return session.get(User, user_id)
    if username:
        return session.exec(select(User).where(User.username == username)).one_or_none()

    return None

def map_user_to_info(user: User) -> UserInfo:
    return UserInfo(
        id=user.id,
        username=user.username,
    )