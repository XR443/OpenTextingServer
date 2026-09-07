# ============= ENUMS =============
import json
import re
from enum import Enum
from typing import Optional, Dict, Any


class Compression(str, Enum):
    GZIP = "gzip"
    ZSTD = "zstd"


class Quality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ============= CONTENT TYPE MODEL =============
class ContentType:
    """Модель для работы с параметризованными MIME-типами"""

    def __init__(
            self,
            mime_type: str,
            encrypted: Optional[bool] = None,
            compression: Optional[Compression] = None,
            quality: Optional[Quality] = None,
            metadata: Optional[Dict[str, Any]] = None,
            **extra_params
    ):
        self.mime_type = mime_type
        self.encrypted = encrypted
        self.compression = compression
        self.quality = quality
        self.metadata = metadata or {}
        self.extra_params = extra_params

        # Валидация MIME-типа
        if not re.match(r'^[a-z]+/[a-z0-9\-+.]+$', mime_type):
            raise ValueError(f"Invalid MIME type: {mime_type}")

    @property
    def full_type(self) -> str:
        """Полный тип: text/plain; encrypted=true; quality=high"""
        parts = [self.mime_type]

        # Добавляем параметры только если они не None
        if self.encrypted is not None:
            parts.append(f"encrypted={str(self.encrypted).lower()}")

        if self.compression is not None:
            parts.append(f"compression={self.compression.value}")

        if self.quality is not None:
            parts.append(f"quality={self.quality.value}")

        # Metadata сериализуем в JSON (если не пусто)
        if self.metadata:
            # Экранируем JSON для безопасного включения в строку
            metadata_str = json.dumps(self.metadata, ensure_ascii=False, separators=(',', ':'))
            parts.append(f"metadata={metadata_str}")

        # Дополнительные параметры
        for key, value in self.extra_params.items():
            parts.append(f"{key}={value}")

        return "; ".join(parts)

    @classmethod
    def from_full_type(cls, full_type: str) -> "ContentType":
        """Парсинг из строки: text/plain; encrypted=true; quality=high"""
        # Разделяем на mime-тип и параметры
        parts = full_type.split("; ")
        mime_type = parts[0].strip()

        params = {}
        for param in parts[1:]:
            if "=" in param:
                key, value = param.split("=", 1)
                params[key.strip()] = value.strip()

        # Парсим известные параметры
        encrypted = None
        if "encrypted" in params:
            encrypted = params["encrypted"].lower() == "true"

        compression = None
        if "compression" in params:
            try:
                compression = Compression(params["compression"])
            except ValueError:
                pass

        quality = None
        if "quality" in params:
            try:
                quality = Quality(params["quality"])
            except ValueError:
                pass
        # Парсим metadata из JSON
        metadata = None
        if "metadata" in params:
            try:
                metadata = json.loads(params["metadata"])
            except json.JSONDecodeError:
                # Если невалидный JSON, сохраняем как строку
                metadata = params["metadata"]
        # Остальные параметры сохраняем как extra
        extra_params = {
            k: v for k, v in params.items()
            if k not in ["encrypted", "compression", "quality"]
        }

        return cls(
            mime_type=mime_type,
            encrypted=encrypted,
            compression=compression,
            quality=quality,
            metadata=metadata,
            **extra_params
        )

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь (только не-None значения)"""
        result = {"mime_type": self.mime_type}

        if self.encrypted is not None:
            result["encrypted"] = self.encrypted
        if self.compression is not None:
            result["compression"] = self.compression.value
        if self.quality is not None:
            result["quality"] = self.quality.value

        result.update(self.extra_params)
        return result

    @classmethod
    def from_headers(
            cls,
            content_type: str,
            encrypted: Optional[bool] = None,
            compression: Optional[str] = None,
            quality: Optional[str] = None,
            metadata: Optional[str] = None,
            **extra_params
    ) -> "ContentType":
        """Создание из заголовков"""
        compression_enum = None
        if compression:
            try:
                compression_enum = Compression(compression)
            except ValueError:
                pass

        quality_enum = None
        if quality:
            try:
                quality_enum = Quality(quality)
            except ValueError:
                pass
        metadata_dict = None
        if metadata:
            try:
                metadata_dict = json.loads(metadata)
            except json.JSONDecodeError:
                metadata_dict = {"raw": metadata}
        return cls(
            mime_type=content_type,
            encrypted=encrypted,
            compression=compression_enum,
            quality=quality_enum,
            metadata=metadata_dict,
            **extra_params
        )


# ============= PRE-DEFINED TYPES =============
class ContentTypes:
    TEXT_PLAIN = ContentType("text/plain")
    TEXT_ENCRYPTED = ContentType("text/plain", encrypted=True)
    VIDEO_MP4 = ContentType("video/mp4")
    VIDEO_MP4_ENCRYPTED = ContentType("video/mp4", encrypted=True)
    VIDEO_MP4_ENCRYPTED_HIGH = ContentType("video/mp4", encrypted=True, quality=Quality.HIGH)
    IMAGE_JPEG = ContentType("image/jpeg")
    IMAGE_JPEG_ENCRYPTED = ContentType("image/jpeg", encrypted=True)
    IMAGE_JPEG_HIGH = ContentType("image/jpeg", quality=Quality.HIGH)
    PDF = ContentType("application/pdf")
    PDF_ENCRYPTED = ContentType("application/pdf", encrypted=True)
    JSON = ContentType("application/json")
    JSON_ENCRYPTED_GZIP = ContentType("application/json", encrypted=True, compression=Compression.GZIP)