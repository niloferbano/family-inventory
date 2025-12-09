# app/apis/homes/service.py

from sqlalchemy.ext.asyncio import AsyncSession
from app.apis.homes.models import Home
from app.apis.homes.repository import HomeRepository
from app.apis.homes.schema import HomeCreate
from app.apis.homeuser.service import HomeUserService
from app.apis.users.models import User


class HomeService:

    def __init__(self, session: AsyncSession, current_user: User):
        self.session = session
        self.current_user = current_user
        self.repo = HomeRepository(session)
        self.home_user_service = HomeUserService(session=session, current_user=current_user)

    async def create_home(self, data: HomeCreate) -> Home:
        if not self.current_user.is_admin:

            has_any_home = await self.home_user_service.user_has_any_home(
                self.current_user.id
            )

            is_owner_anywhere = await self.home_user_service.user_is_owner_anywhere(
                self.current_user.id
            )

            if has_any_home and not is_owner_anywhere:
                raise PermissionError(
                    "Residents and guests cannot create homes."
                )
        if await self.repo.get_by_name(data.name):
            raise ValueError("Home with this name already exists")

        home = Home(name=data.name)
        home = await self.repo.create(home)
        # await self.home_user_service.create_owner_for_home(home.id)
        return home

    async def get_home_for_user(self, home_id: int):
        home = await self.repo.get_for_user(
            home_id=home_id,
            user_id=self.current_user.id,
            is_admin=self.current_user.is_admin,
        )
        if not home:
            raise PermissionError("You are not allowed to access this home")
        return home