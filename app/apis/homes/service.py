# app/apis/homes/service.py

from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.homes.models import Home
from app.apis.homes.repository import HomeRepository
from app.apis.homes.schema import HomeCreate
from app.apis.homeuser.repository import HomeUserRepository
from app.apis.users.models import User


class HomeService:

    def __init__(self, session: AsyncSession, current_user: User):
        self.session = session
        self.current_user = current_user
        self.home_repo = HomeRepository(session)
        self.home_user_repo = HomeUserRepository(session)

    async def create_home(self, data: HomeCreate) -> Home:
        home = await self.home_repo.create(Home(name=data.name))
        await self.home_user_repo.assign_owner(
            home_id=home.id, user_id=self.curremt_user.id
        )
        return home

    async def get_home_for_user(self, home_id: int):
        home = await self.home_repo.get_for_user(
            home_id=home_id,
            user_id=self.current_user.id,
            is_admin=self.current_user.is_admin,
        )
        if not home:
            raise PermissionError("You are not allowed to access this home")
        return home
