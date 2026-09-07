import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import Column, BINARY
from sqlmodel import SQLModel, Field, Relationship


class Key(SQLModel, table=True):
    user: uuid.UUID = Field(primary_key=True)
    public_key: bytes | None = Field(sa_column=Column(BINARY))


# Модель для ответа с информацией о пользователе
class KeyWithUserInfo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel,validate_by_name=True)

    user_id: uuid.UUID
    username: str
