from math import ceil

from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.homes.models import Home
from app.apis.homes.repository import HomeRepository
from app.apis.homes.schema import (GetHomesResponse,
                                   GetHomeWithMembersResponse, HomeCreate,
                                   PaginatedAdminHomesResponse)
from app.apis.homeuser.repository import HomeUserRepository
from app.apis.users.models import User
from app.core.database.base import HomeId
from app.core.database.pagination import Page, update_pagination


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

    async def get_home_for_user(self, home_id: HomeId):
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
        homes_by_id: dict[HomeId, GetHomeWithMembersResponse] = {}

        for home, member_user, member_role in result:
            if home.id not in homes_by_id:
                homes_by_id[home.id] = GetHomeWithMembersResponse(
                    home_id=home.id, name=home.name, members=[]
                )

            homes_by_id[home.id].members.append(
                GetHomesResponse(
                    user_id=member_user.id,
                    username=member_user.username,
                    email=member_user.email,
                    user_type=member_role,
                )
            )

        return list(homes_by_id.values())

    async def get_all_homes_admin(
        self,
        pagination: Page,
        request_url: str,
    ) -> PaginatedAdminHomesResponse:

        rows, total = await self.home_repo.get_all_homes_with_members(pagination)

        homes: dict[HomeId, GetHomeWithMembersResponse] = {}

        for (
            home_id,
            name,
            created_at,
            updated_at,
            user_id,
            username,
            email,
            user_type,
        ) in rows:
            if home_id not in homes:
                homes[home_id] = GetHomeWithMembersResponse(
                    home_id=home_id,
                    name=name,
                    created_at=created_at,
                    updated_at=updated_at,
                    members=[],
                )

            homes[home_id].members.append(
                GetHomesResponse(
                    user_id=user_id,
                    username=username,
                    email=email,
                    user_type=user_type.value,
                )
            )

        total_pages = ceil(total / pagination.page_size)

        next_url = (
            update_pagination(request_url, pagination.page + 1, pagination.page_size)
            if pagination.page < total_pages
            else None
        )

        prev_url = (
            update_pagination(request_url, pagination.page - 1, pagination.page_size)
            if pagination.page > 1
            else None
        )

        return PaginatedAdminHomesResponse(
            count=total,
            total_pages=total_pages,
            next=next_url,
            previous=prev_url,
            results=list(homes.values()),
        )
