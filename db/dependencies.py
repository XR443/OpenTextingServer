import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine

# todo migrate to normal db
sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)

logger = logging.getLogger(__name__)

def create_db_and_tables():
    """Создает таблицы безопасно - проверяет существование"""
    try:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())

        # Получаем имена всех моделей
        all_models = SQLModel.metadata.tables.keys()

        # Проверяем, какие таблицы нужно создать
        tables_to_create = [table for table in all_models if table not in existing_tables]

        if tables_to_create:
            logger.info(f"Creating tables: {tables_to_create}")
            SQLModel.metadata.create_all(engine)
            logger.info("✅ Tables created successfully")
        else:
            logger.info("ℹ️ All tables already exist")

    except Exception as e:
        logger.error(f"Error with database: {e}")
        # Если ошибка - пробуем создать все таблицы
        try:
            SQLModel.metadata.create_all(engine)
            logger.info("✅ Tables created (force)")
        except Exception as e2:
            logger.error(f"Failed to create tables: {e2}")
            raise

def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
