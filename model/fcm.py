import uuid
from typing import List

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import Column
from sqlmodel import Field, SQLModel, Relationship


class FCMTokenDB(SQLModel, table=True):
    """Модель для БД"""
    __tablename__ = "fcm_tokens"
    account_id: uuid.UUID = Field(primary_key=True)  # составной ключ
    fcm_token: str = Field(primary_key=True)  # составной ключ

# ========== МОДЕЛЬ ЗАПРОСА ==========
class FCMRegisterRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel,validate_by_name=True)

    account_ids: List[uuid.UUID] = Field(min_length=1)
    fcm_token: str


# ========== МОДЕЛЬ ОТВЕТА ==========
class FCMRegisterResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel,validate_by_name=True)

    success: bool
    registered: int
    failed: List[uuid.UUID] = []