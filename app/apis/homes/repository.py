from sqlalchemy.ext.asyncio import AsyncSession
from app.apis.homes.models import Home
from app.apis.homes.queries import (
    query_get_home_by_id,
    query_get_home_by_name,
    query_get_home_for_user,
)
from sqlalchemy.exc import IntegrityError


class HomeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, home: Home) -> Home:
        self.session.add(home)
        try:
            await self.session.flush()
        except IntegrityError:
            raise ValueError("Home with this name already exists")
        return home

    async def get_by_name(self, name: str) -> Home | None:
        query = query_get_home_by_name(name)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    async def get_by_id(self, home_id: int):
        stmt = query_get_home_by_id(home_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_user(self, home_id: int, user_id: int, is_admin: bool):
        stmt = query_get_home_for_user(home_id, user_id, is_admin)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()