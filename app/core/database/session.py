from functools import lru_cache
from typing import AsyncGenerator, Type

from fastapi import Depends
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession,
                                    async_sessionmaker, create_async_engine)
from sqlalchemy.orm import DeclarativeBase

from app.core.configs.config import settings
from app.core.database.base import SQLBase


class DBManager:
    def __init__(self, model_base: Type[DeclarativeBase], db_url: str | URL, **kwargs):
        self.model_base = model_base
        print("✅ CONNECTING TO DATABASE:", db_url)
        # MUST specify future=True for async
        self.engine: AsyncEngine = create_async_engine(
            db_url, echo=True, future=True, **kwargs
        )

        # async sessionmaker MUST use class_=AsyncSession
        self.sessionmaker = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def connect(self):
        conn = await self.engine.connect()
        await conn.close()

    async def disconnect(self):
        await self.engine.dispose()

    async def ping(self):
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def create_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(self.model_base.metadata.create_all)

    async def drop_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(self.model_base.metadata.drop_all)

    async def truncate_tables(self):
        async with self.engine.begin() as conn:
            tables = ",".join(
                table.name for table in reversed(self.model_base.metadata.sorted_tables)
            )
            await conn.execute(
                text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE;")
            )

    def get_session(self):
        return self.sessionmaker()

    def begin(self):
        return self.sessionmaker.begin()


@lru_cache
def get_db() -> DBManager:
    return DBManager(
        model_base=SQLBase,
        db_url=settings.DATABASE_URL,
        pool_size=10,
        # max_overflow=20,
    )


async def get_session(
    db: DBManager = Depends(get_db),
) -> AsyncGenerator[AsyncSession, None]:
    async with db.sessionmaker() as session:
        yield session
