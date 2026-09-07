import struct
import struct
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import update, asc
from sqlmodel import select, or_, and_, desc
from starlette import status
from starlette.responses import StreamingResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

from db import SessionDep
from model import Status, get_user, ConnectionManagerDep, FCMTokenDB
from model.content import ContentType
from model.message import Message, MessageInfo, map_message_to_info
from security import CurrentUserDep
from security.dependencies import get_current_user

router = APIRouter(
    prefix="/messages",
    tags=["messages"],
    responses={404: {"description": "Not found"}},
)


@router.websocket("/new/notification/ws")
async def websocket_endpoint(websocket: WebSocket, session: SessionDep, connection_manager: ConnectionManagerDep):
    headers = websocket.headers
    user = await get_current_user(headers["authorization"][len("Bearer "):], session)
    connection_manager.disconnect(user)
    await connection_manager.connect(user, websocket)
    try:
        while True:
            # Просто ждем сообщения, ничего с ними не делаем
            recieved = await websocket.receive()
            print(recieved)
    except WebSocketDisconnect as e:
        print("WebSocket disconnected for:", e)
        connection_manager.disconnect(user)
    except RuntimeError as e:
        print("WebSocket disconnected for:", e)
        connection_manager.disconnect(user)


@router.post("/{message_id}", response_model=MessageInfo)
async def message_info(message_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep):
    user_clause = or_(Message.author == current_user, Message.recipient == current_user)
    statement = select(Message.payload).where(Message.id == message_id, user_clause)
    message = session.exec(statement).one_or_none()
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return message


# Модель для входящего запроса
class MessageRequest(BaseModel):
    ids: List[uuid.UUID]  # Список UUID записей, которые нужно отдать


@router.post("/data/stream")
async def get_messages_stream(ids_dto: MessageRequest, session: SessionDep, current_user: CurrentUserDep):
    """
    POST метод, возвращающий поток байт с сообщениями.
    Формат: [UUID (16 байт)][Размер сообщения (4 байта)][Сообщение]
    """

    # Проверяем, что запрос не пустой
    if not ids_dto.ids:
        raise HTTPException(status_code=400, detail="No IDs provided")

    # Пытаемся получить сообщение
    user_clause = or_(Message.author == current_user, Message.recipient == current_user)
    statement = select(Message).where(Message.id.in_(ids_dto.ids), user_clause)

    messages: List[Message] = session.exec(statement).all()

    def generate_stream():
        """Генератор байтового потока"""
        for message in messages:
            try:
                message_bytes = message.payload

                if message_bytes is None:
                    # Если сообщение не найдено, пропускаем его
                    # Можно также передать пустое сообщение с размером 0
                    continue

                # Проверяем валидность UUID
                try:
                    # Преобразуем строковый UUID в 16-байтовое представление
                    uuid_bytes = message.id.bytes
                except ValueError:
                    # Если UUID невалидный, пропускаем запись
                    continue

                # Получаем размер сообщения (4 байта, big-endian)
                msg_size = len(message_bytes)
                # Используем знаковый int (big-endian)
                # '>i' = знаковый int, 4 байта, big-endian
                size_bytes = struct.pack('>i', msg_size)

                # Отправляем данные в формате:
                # [16 байт UUID][4 байта размер][сообщение]
                yield uuid_bytes
                yield size_bytes
                yield message_bytes

            except Exception as e:
                # Логируем ошибку, но продолжаем обработку остальных записей
                print(f"Error processing message {message.id}: {e}")
                continue

    # Возвращаем StreamingResponse с правильным медиа-типом
    return StreamingResponse(
        generate_stream(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename=messages.bin",
            "X-Content-Type-Options": "nosniff",
        }
    )


# DTO для запроса
class MessageQuery(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,  # позволяет использовать как snake_case, так и camelCase
        extra='forbid'  # запрещаем лишние поля
    )
    message_id: Optional[uuid.UUID] = Field(
        default=None,
        alias='messageId'  # в JSON будет messageId
    )
    date_from: Optional[datetime] = Field(
        default=None,
        alias='dateFrom'  # в JSON будет dateFrom
    )
    delta: int = Field(
        default=50,
        ge=1,
        alias='delta'  # оставляем как delta (или можно оставить без alias)
    )


# Альтернативная версия с использованием подзапросов для большей эффективности
@router.post("/with/{user_id}", response_model=List[MessageInfo])
async def get_messages_by_delta_efficient(
        user_id: uuid.UUID,
        session: SessionDep,
        current_user: CurrentUserDep,
        query: MessageQuery = MessageQuery(delta=50)
):
    other_user = get_user(session, user_id=user_id)
    if not other_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Фильтр для сообщений между пользователями
    conversation_filter = or_(
        and_(Message.author == current_user, Message.recipient == other_user),
        and_(Message.author == other_user, Message.recipient == current_user)
    )

    # Определяем центральное сообщение и дату
    center_message = None
    center_date = None

    # Приоритет: message_id > date_from > непрочитанное > последнее
    if query.message_id:
        # 1. Ищем по ID сообщения
        center_message = session.exec(
            select(Message).where(
                and_(Message.id == query.message_id, conversation_filter)
            )
        ).first()

        if not center_message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found or not in conversation"
            )
        center_date = center_message.created_at

    elif query.date_from:
        # 2. Ищем по дате - находим ближайшее сообщение к указанной дате
        # Ищем сообщение, которое было отправлено до или в указанную дату (ближайшее снизу)
        center_message = session.exec(
            select(Message)
            .where(
                and_(
                    conversation_filter,
                    Message.created_at <= query.date_from
                )
            )
            .order_by(desc(Message.created_at))
            .limit(1)
        ).first()

        if not center_message:
            # Если нет сообщений до даты, берем самое первое сообщение
            center_message = session.exec(
                select(Message)
                .where(conversation_filter)
                .order_by(asc(Message.created_at))
                .limit(1)
            ).first()

            if not center_message:
                return []

        center_date = center_message.created_at

    else:
        # 3. Ищем последнее непрочитанное сообщение
        center_message = session.exec(
            select(Message)
            .where(
                and_(
                    conversation_filter,
                    Message.status != Status.READ
                )
            )
            .order_by(desc(Message.created_at))
            .limit(1)
        ).first()

        if center_message:
            center_date = center_message.created_at
        else:
            # 4. Если непрочитанных нет, берем последнее сообщение в диалоге
            center_message = session.exec(
                select(Message)
                .where(conversation_filter)
                .order_by(desc(Message.created_at))
                .limit(1)
            ).first()

            if not center_message:
                return []  # Нет сообщений в диалоге

            center_date = center_message.created_at

    # Получаем все сообщения до центра (включая центральное)
    before_messages = session.exec(
        select(Message)
        .where(
            and_(
                conversation_filter,
                Message.created_at <= center_date
            )
        )
        .order_by(desc(Message.created_at))
        .limit(query.delta + 1)  # +1 чтобы включить центральное сообщение
    ).all()

    # Переворачиваем обратно, чтобы были в хронологическом порядке
    # todo сортировка на клиенте?
    # before_messages.reverse()

    # Получаем сообщения после центра (исключая центральное)
    after_messages = session.exec(
        select(Message)
        .where(
            and_(
                conversation_filter,
                Message.created_at > center_date
            )
        )
        .order_by(asc(Message.created_at))
        .limit(query.delta)
    ).all()

    # Объединяем сообщения
    all_messages = before_messages + after_messages

    return [map_message_to_info(msg) for msg in all_messages]


@router.post("/read/{message_id}", response_model=List[MessageInfo])
async def read_message(message_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep):
    update_clause = and_(Message.id == message_id, Message.recipient == current_user)

    message = session.exec(select(Message).where(update_clause)).one_or_none()

    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    update_clause = and_(
        Message.recipient == current_user,
        Message.created_at <= message.created_at,
        Message.status != Status.READ
    )

    message_ids = session.exec(select(Message.id).where(update_clause)).all()

    session.exec(update(Message).where(update_clause).values(status=Status.READ))

    messages = session.exec(select(Message).where(Message.id.in_(message_ids)))

    session.commit()

    return map(map_message_to_info, messages)


# todo load last n to k messages


@router.post("/to/{recipient_id}", response_model=MessageInfo)
async def message_to(
        recipient_id: uuid.UUID,
        request: Request,
        session: SessionDep,
        current_user: CurrentUserDep,
        background_tasks: BackgroundTasks,
        connection_manager: ConnectionManagerDep,
        x_content_type: str = Header(description="MIME тип: video/mp4, text/plain"),
        x_encrypted: Optional[str] = Header(None, description="true/false"),
        x_compression: Optional[str] = Header(None, description="gzip, zstd"),
        x_quality: Optional[str] = Header(None, description="low, medium, high"),
        x_metadata: Optional[str] = Header(None, description='JSON метаданных: {"key":"value"}')
):
    body = await request.body()

    recipient = get_user(session, user_id=recipient_id)
    if not recipient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # 1. Создаем ContentType из заголовков
    encrypted_bool = None
    if x_encrypted is not None:
        encrypted_bool = x_encrypted.lower() == "true"

    content_type = ContentType.from_headers(
        content_type=x_content_type,
        encrypted=encrypted_bool,
        compression=x_compression,
        quality=x_quality,
        x_metadata=x_metadata
    )

    message = Message(id=uuid.uuid4(),  # todo v7
                      author=current_user, recipient=recipient,
                      payload=body, format=content_type.full_type, status=Status.SENDING,
                      created_at=datetime.now(timezone.utc))

    session.add(message)
    session.commit()

    # todo доделать до фонового процесса
    tokens = session.exec(select(FCMTokenDB.fcm_token).where(FCMTokenDB.account_id == recipient.id)).all()
    background_tasks.add_task(connection_manager.send_notify, current_user, recipient, tokens)

    return map_message_to_info(message, False)
    # try:
    #     return MessageInfo(id=message.id,
    #                    author=UserInfo(
    #                        id=message.author.id,
    #                        username=message.author.username,
    #                    ),
    #                    recipient=UserInfo(
    #                        id=message.recipient.id,
    #                        username=message.recipient.username,
    #                    ),
    #                    payload_type=message.payload_type,
    #                    status=message.status,
    #                    created_at=message.created_at,
    #                    updated_at=message.updated_at,
    #                    )
    # except ValidationError as e:
    #     print("Missing fields:")
    #     for error in e.errors():
    #         print(f"- {error['loc'][0]}: {error['msg']}")
    #     raise
