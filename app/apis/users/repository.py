import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User
from .queries import count_active_users_query, get_user_by_email_query


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ORM CRUD
    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    def get_all_query(self) -> sa.Select:
        return sa.select(User)

    # Query Object Pattern (Core)
    async def get_by_email(self, email: str) -> User | None:
        query = get_user_by_email_query(email)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def count_active_users(self) -> int:
        query = count_active_users_query()
        result = await self.session.execute(query)
        return result.scalar_one()
