# app/apis/homes/service.py

from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.homes.models import Home
from app.apis.homes.repository import HomeRepository
from app.apis.homes.schema import (GetHomesResponse,
                                   GetHomeWithMembersResponse, HomeCreate)
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
            home_id=home.id, user_id=self.current_user.id
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

    async def get_all_homes_for_user(self) -> list[GetHomeWithMembersResponse]:
        user_owned_home_ids = await self.home_user_repo.get_home_ids_for_owner(
            self.current_user.id
        )
        if not user_owned_home_ids:
            return []
        result = await self.home_repo.get_homes_with_members_for_owner(
            home_ids=user_owned_home_ids
        )
        homes_by_id: dict[int, GetHomeWithMembersResponse] = {}

        for home, member_user, member_role in result:
            if home.id not in homes_by_id:
                homes_by_id[home.id] = GetHomeWithMembersResponse(
                    id=home.id, name=home.name, members=[]
                )

            homes_by_id[home.id].members.append(
                GetHomesResponse(
                    id=member_user.id,
                    username=member_user.username,
                    email=member_user.email,
                    role=member_role,
                )
            )

        return list(homes_by_id.values())
