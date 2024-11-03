import os

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from sqlalchemy import insert, update, delete

# from core.database.models import Account, AccountStatistics, Node


# Создаем асинхронный движок для работы с базой данных SQLite
db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/test.db'))
DATABASE_URL = fr"sqlite+aiosqlite:///{db_path}"

engine = create_async_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def create_db():
    import sqlite3

    sqlite3.connect(db_path).close()





async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()

create_db()
