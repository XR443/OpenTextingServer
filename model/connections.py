import json
import logging
import os
from typing import Optional, List
from uuid import UUID

from starlette.websockets import WebSocket, WebSocketDisconnect
from sqlmodel import Session, select

from model import User

# Импорты для FCM
from firebase_admin import messaging, initialize_app, credentials
import firebase_admin

logger = logging.getLogger(__name__)


class FCMService:
    """Сервис для работы с FCM уведомлениями"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._init_firebase()
            FCMService._initialized = True

    def _init_firebase(self):
        """Инициализация Firebase Admin SDK"""
        try:
            cred = credentials.Certificate(os.getenv(
                "FIREBASE_SERVICE_ACCOUNT_PATH",
                "serviceAccountKey.json"  # значение по умолчанию
            ))
            firebase_admin.initialize_app(cred)
            logger.info("Firebase initialized successfully")
        except Exception as e:
            try:
                firebase_admin.initialize_app()
                logger.info("Firebase initialized with default credentials")
            except Exception as e2:
                logger.error(f"Failed to initialize Firebase: {e2}")
                raise

    async def send_notification(
            self,
            account_id: UUID,
            fcm_token: str,
            title: str = "Новое уведомление",
            body: str = "У вас новое сообщение",
            data: Optional[dict] = None
    ) -> bool:
        """
        Отправка FCM уведомления

        Args:
            account_id: ID аккаунта получателя
            fcm_token: FCM токен устройства получателя
            title: Заголовок уведомления
            body: Текст уведомления
            data: Дополнительные данные (словарь)

        Returns:
            bool: Успешность отправки
        """
        try:
            if not fcm_token:
                logger.warning(f"No FCM token for account {account_id}")
                return False
            message = messaging.Message(
                # 1. Notification на верхнем уровне - ЭТО ГЛАВНОЕ ДЛЯ ВСПЛЫВАЮЩИХ УВЕДОМЛЕНИЙ
                notification=messaging.Notification(
                    title=title,
                    body=body,
                    image=None
                ),

                # 2. Данные (будут доступны в приложении)
                data=data or {},

                # 3. Токен устройства
                token=fcm_token,

                # 4. Android настройки
                android=messaging.AndroidConfig(
                    priority="high",  # high - обязательно для всплывающих
                    notification=messaging.AndroidNotification(
                        title=title,
                        body=body,
                        icon="ic_launcher",
                        color="#FF0000",
                        sound="default",
                        priority="high",
                        default_sound=True,
                        default_vibrate_timings=True,
                        sticky=False,
                        click_action="OPEN_ACTIVITY",
                        channel_id="open_texting_message",  # Должен существовать в приложении
                        tag="notification_tag",
                        image=None,
                        visibility="public",
                        # notification_count=1,
                        # timeout=5000,  # Время жизни уведомления
                    ),
                ),

                # 5. iOS настройки
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            alert=messaging.ApsAlert(
                                title=title,
                                body=body
                            ),
                            sound="default",
                            badge=1,
                            content_available=True,
                            mutable_content=True,
                            category="NEW_MESSAGE",
                        )
                    ),
                    fcm_options=messaging.APNSFCMOptions(
                        image= None
                    )
                ),
            )
            # response = await messaging.send(message)
            response = messaging.send(message)
            logger.info(f"FCM notification sent to account {account_id}: {response}")
            return True

        except messaging.UnregisteredError:
            logger.warning(f"FCM token invalid for account {account_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to send FCM notification to account {account_id}: {e}")
            return False


class ConnectionManager:
    def __init__(self):
        """
        Инициализация менеджера соединений
        """
        self.active_connections: dict[str, WebSocket] = dict()  # account_id -> websocket
        self.fcm_service = FCMService()

    async def connect(self, user: User, websocket: WebSocket):
        """Подключение пользователя по вебсокету"""
        await websocket.accept()
        account_id = str(user.id)
        self.active_connections[account_id] = websocket
        logger.info(f"User {account_id} connected via WebSocket")

    def disconnect(self, user: User):
        """Отключение пользователя"""
        account_id = str(user.id)
        if account_id in self.active_connections:
            try:
                self.active_connections.pop(account_id).close()
                logger.info(f"User {account_id} disconnected")
            except Exception as e:
                logger.error(f"Error closing websocket for {account_id}: {e}")

    async def send_notify(
            self,
            author: User,
            recipient: User,
            fcm_tokens: List[str] = None,  # FCM токен получателя
            message: Optional[str] = None,
            data: Optional[dict] = None,
            save_token: bool = True  # Сохранять ли токен в БД
    ) -> bool:
        """
        Отправка уведомления пользователю

        Args:
            author: Отправитель
            recipient: Получатель
            fcm_tokens: FCM токен получателя (если None - берем из БД)
            message: Текст сообщения
            title: Заголовок для FCM уведомления
            data: Дополнительные данные для FCM
            save_token: Сохранять ли переданный токен в БД

        Returns:
            bool: Успешность отправки
        """
        recipient_id = str(recipient.id)
        author_id = str(author.id)
        recipient_uuid = UUID(recipient_id)

        # Подготовка данных для отправки
        ws_data = {
            "message_from": author_id,
            "message": message or "",
            "type": "notification",
            "timestamp": await self._get_current_timestamp()
        }

        # 1. Пытаемся отправить через вебсокет
        ws_success = False
        if recipient_id in self.active_connections:
            try:
                await self.active_connections[recipient_id].send_text(
                    json.dumps(ws_data)
                )
                ws_success = True
                logger.info(f"Notification sent via WebSocket to {recipient_id}")
            except WebSocketDisconnect:
                self.disconnect(recipient)
                logger.info(f"WebSocket disconnected for {recipient_id}, trying FCM")
            except Exception as e:
                logger.error(f"Error sending via WebSocket to {recipient_id}: {e}")
        else:
            logger.info(f"WebSocket not connected for {recipient_id}, trying FCM")

        # 2. Если вебсокет недоступен, отправляем через FCM
        if not ws_success:
            if not fcm_tokens:
                logger.warning(f"No FCM tokens found for user {recipient_id}")
                return False

            # Подготовка данных для FCM
            sender_name = author.username or "Пользователь"
            fcm_data = {
                "sender_id": author_id,
                "sender_name": sender_name,
                "type": "message",
                "message": message or "",
                **(data or {})
            }

            # Отправка на все устройства
            fcm_success = False
            for token in fcm_tokens:
                success = await self.fcm_service.send_notification(
                    account_id=recipient_uuid,
                    fcm_token=token,
                    title=sender_name,
                    body=message or "У вас новое сообщение",
                    data=fcm_data
                )

            return fcm_success

        return True

    async def send_notify_with_fallback(
            self,
            author: User,
            recipient: User,
            fcm_tokens: List[str] = None,
            message: Optional[str] = None,
            title: str = "Новое сообщение",
            data: Optional[dict] = None,
            force_fcm: bool = False  # Принудительно отправить через FCM даже при открытом WS
    ) -> dict:
        """
        Отправка уведомления с полной статистикой

        Returns:
            dict: Статистика отправки
        """
        recipient_id = str(recipient.id)
        result = {
            "recipient_id": recipient_id,
            "websocket_sent": False,
            "fcm_sent": False,
            "fcm_tokens_used": [],
            "errors": []
        }

        # 1. Отправка через вебсокет
        if not force_fcm and recipient_id in self.active_connections:
            try:
                ws_data = {
                    "message_from": str(author.id),
                    "message": message or "",
                    "type": "notification",
                    "timestamp": await self._get_current_timestamp()
                }
                await self.active_connections[recipient_id].send_text(
                    json.dumps(ws_data)
                )
                result["websocket_sent"] = True
                logger.info(f"WebSocket notification sent to {recipient_id}")
                return result  # Если WS успешно отправлен, не отправляем FCM
            except Exception as e:
                result["errors"].append(f"WebSocket error: {str(e)}")
                logger.error(f"WebSocket error for {recipient_id}: {e}")

        # 2. Отправка через FCM
        recipient_uuid = UUID(recipient_id)

        if not fcm_tokens:
            result["errors"].append("No FCM tokens available")
            return result

        fcm_data = {
            "sender_id": str(author.id),
            "sender_name": author.username or "Пользователь",
            "type": "message",
            "message": message or "",
            **(data or {})
        }

        for token in fcm_tokens:
            success = await self.fcm_service.send_notification(
                account_id=recipient_uuid,
                fcm_token=token,
                title=title,
                body=message or "У вас новое сообщение",
                data=fcm_data
            )

            if success:
                result["fcm_sent"] = True
                result["fcm_tokens_used"].append(token[:10] + "...")  # Маскируем токен для логов
            else:
                result["errors"].append(f"FCM failed for token {token[:10]}...")

        return result

    async def send_notify_to_multiple(
            self,
            author: User,
            recipients_with_tokens: List[tuple],  # List[(User, Optional[str])]
            message: Optional[str] = None,
            title: str = "Новое сообщение",
            data: Optional[dict] = None
    ) -> dict:
        """
        Отправка уведомления нескольким пользователям с их токенами

        Args:
            author: Отправитель
            recipients_with_tokens: Список кортежей (User, fcm_token)
            message: Текст сообщения
            title: Заголовок для FCM уведомления
            data: Дополнительные данные

        Returns:
            dict: Статистика отправки
        """
        stats = {
            "total": len(recipients_with_tokens),
            "websocket_success": 0,
            "fcm_success": 0,
            "failed": 0,
            "details": {}
        }

        for recipient, fcm_token in recipients_with_tokens:
            try:
                success = await self.send_notify(
                    author=author,
                    recipient=recipient,
                    fcm_token=fcm_token,
                    message=message,
                    title=title,
                    data=data
                )

                recipient_id = str(recipient.id)
                if success:
                    if recipient_id in self.active_connections:
                        stats["websocket_success"] += 1
                    else:
                        stats["fcm_success"] += 1
                    stats["details"][recipient_id] = "success"
                else:
                    stats["failed"] += 1
                    stats["details"][recipient_id] = "failed"

            except Exception as e:
                stats["failed"] += 1
                stats["details"][str(recipient.id)] = f"error: {str(e)}"
                logger.error(f"Error sending to {recipient.id}: {e}")

        logger.info(f"Notification stats: {stats}")
        return stats

    async def _get_current_timestamp(self):
        """Получение текущей временной метки"""
        from datetime import datetime
        return datetime.utcnow().isoformat()

    def is_websocket_connected(self, user_id: str) -> bool:
        """Проверка, подключен ли пользователь по вебсокету"""
        return user_id in self.active_connections

    def get_connected_users(self) -> List[str]:
        """Получение списка подключенных пользователей"""
        return list(self.active_connections.keys())
