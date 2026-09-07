import base64
from contextlib import asynccontextmanager

import uvicorn
# from Crypto.Cipher import PKCS1_OAEP
# from Crypto.PublicKey import RSA
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from db.dependencies import create_db_and_tables
from routers import messages, security, chats, fcm


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

# Настройка через параметры приложения
app.model_config = {
    "alias_generator": to_camel,
    "populate_by_name": True
}

# Применяем ко всем моделям через настройки
BaseModel.model_config = ConfigDict(
    alias_generator=to_camel,
    populate_by_name=True
)

app.include_router(messages.router)
app.include_router(security.router)
app.include_router(chats.router)
app.include_router(fcm.router)

# private_key = RSA.generate(2048)
# public_key = private_key.publickey()
#
# PUBLIC_KEY_PEM = public_key.export_key()
# PRIVATE_KEY_PEM = private_key.export_key()
#
#
# def encrypt_aes_key_with_rsa(aes_key: bytes) -> str:
#     """Шифруем AES ключ с помощью RSA"""
#     cipher_rsa = PKCS1_OAEP.new(RSA.import_key(PUBLIC_KEY_PEM))
#     encrypted_key = cipher_rsa.encrypt(aes_key)
#     return base64.b64encode(encrypted_key).decode('utf-8')
#
#
# def decrypt_aes_key_with_rsa(encrypted_key_b64: str) -> bytes:
#     """Расшифровываем AES ключ с помощью RSA"""
#     encrypted_key = base64.b64decode(encrypted_key_b64)
#     cipher_rsa = PKCS1_OAEP.new(RSA.import_key(PRIVATE_KEY_PEM))
#     return cipher_rsa.decrypt(encrypted_key)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
