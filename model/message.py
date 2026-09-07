import datetime
import uuid
from enum import Enum

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import LargeBinary, Column, DateTime, ForeignKey
from sqlmodel import Field, SQLModel, Relationship

from .user import User, UserInfo

class Status(Enum):
    SENDING = "sending"  # отправка получателю
    CONFIRMED = "confirmed"  # сообщение отправлено
    READ = "read"  # прочитано


class MessageBase(SQLModel):
    id: uuid.UUID = Field(primary_key=True)

    author_id: uuid.UUID | None = Field(default=None, index=True, foreign_key="user.id")
    recipient_id: uuid.UUID | None = Field(default=None, index=True, foreign_key="user.id")

    format: str = Field()

    status: Status = Field()

    created_at: datetime.datetime = Field(sa_column=Column(DateTime(timezone=True)))
    updated_at: datetime.datetime | None = Field(sa_column=Column(DateTime(timezone=True)))


class Message(MessageBase, table=True):
    payload: bytes = Field(sa_column=Column(LargeBinary))

    author: User = Relationship(back_populates="outbox",
                                sa_relationship_kwargs={"foreign_keys": "Message.author_id"})
    recipient: User = Relationship(back_populates="inbox",
                                   sa_relationship_kwargs={"foreign_keys": "Message.recipient_id"})


class MessageInfo(MessageBase):
    model_config = ConfigDict(alias_generator=to_camel,validate_by_name=True)
    id: uuid.UUID

    author_id: uuid.UUID
    recipient_id: uuid.UUID

    format: str

    status: Status

    created_at: datetime.datetime
    updated_at: datetime.datetime | None


def map_message_to_info(message: Message, map_payload=True) -> MessageInfo:
    return MessageInfo(
        id=message.id,
        author_id=message.author.id,
        recipient_id=message.recipient.id,
        format=message.format,
        status=message.status,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )
