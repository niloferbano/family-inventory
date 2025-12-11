# app/apis/homeuser/repository.py
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.homeuser.models import HomeUser, UserType
from app.core.database.base import HomeId, UserId


class HomeUserRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def assign_owner(self, user_id: UserId, home_id: HomeId) -> None:
        link = HomeUser(
            user_id=user_id,
            home_id=home_id,
            user_type=UserType.OWNER,
        )
        self.session.add(link)

    async def add(self, homeuser: HomeUser) -> HomeUser:
        self.session.add(homeuser)
        await self.session.flush()
        return homeuser

    async def get(self, user_id: UserId, home_id: HomeId) -> HomeUser | None:
        stmt = sa.select(HomeUser).where(
            sa.and_(HomeUser.user_id == user_id, HomeUser.home_id == home_id)
        )
        return await self.session.scalar(stmt)

    async def list_for_home(self, home_id: HomeId):
        stmt = sa.select(HomeUser).where(HomeUser.home_id == home_id)
        return (await self.session.scalars(stmt)).all()

    async def get_all_user_homes(self, user_id: UserId):
        stmt = sa.select(HomeUser.home_id).where(
            sa.and_(HomeUser.user_id == user_id, HomeUser.user_type == UserType.OWNER)
        )
        return await self.session.scalars(stmt).all()

    async def user_has_access(self, user_id: UserId, home_id: HomeId) -> bool:
        return bool(await self.get(user_id, home_id))

    async def user_is_owner(self, user_id: UserId, home_id: HomeId) -> bool:
        query = sa.select(HomeUser).where(
            HomeUser.user_id == user_id,
            HomeUser.home_id == home_id,
            HomeUser.user_type == UserType.OWNER,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None

    async def get_home_ids_for_owner(self, user_id: UserId) -> list[int]:
        stmt = sa.select(HomeUser.home_id).where(
            HomeUser.user_id == user_id,
            HomeUser.user_type == UserType.OWNER,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
