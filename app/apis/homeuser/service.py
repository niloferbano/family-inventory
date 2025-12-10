# app/apis/homeuser/service.py
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.homes.repository import HomeRepository
from app.apis.homeuser.exceptions import (AlreadyMemberException,
                                          TargetUserDoesnotExists)
from app.apis.homeuser.models import HomeUser, UserType
from app.apis.homeuser.repository import HomeUserRepository
from app.apis.homeuser.schema import HomeUserAddResponse
from app.apis.users.models import User
from app.apis.users.repository import UserRepository


class HomeUserService:

    def __init__(self, session: AsyncSession, current_user: User):
        self.repo = HomeUserRepository(session)
        self.user_repo = UserRepository(session)
        self.home_repo = HomeRepository(session)
        self.current_user = current_user

    async def create_owner_for_home(self, home_id: int) -> HomeUser:
        existing = await self.repo.get(self.current_user.id, home_id)
        if existing:
            return existing

        home_user = HomeUser(
            user_id=self.current_user.id,
            home_id=home_id,
            user_type=UserType.OWNER,
        )
        return await self.repo.add(home_user)

    async def add_user_to_home(
        self,
        home_id: int,
        target_user_email: EmailStr,
        user_type: UserType,
    ) -> HomeUserAddResponse:

        if user_type == UserType.OWNER:
            raise ValueError("Owners can only be created during home creation.")
        home = await self.home_repo.get_by_id(home_id=home_id)
        target_user = await self.user_repo.get_by_email(email=target_user_email)
        if not target_user:
            raise TargetUserDoesnotExists()

        is_owner = await self.repo.user_is_owner(self.current_user.id, home_id)

        if not (self.current_user.is_admin or is_owner):
            raise PermissionError("Not allowed to add users to this home.")

        existing = await self.repo.get(target_user.id, home_id)
        if existing:
            raise AlreadyMemberException()

        home_user = HomeUser(
            user_id=target_user.id,
            home_id=home_id,
            user_type=user_type,
        )

        home_user = await self.repo.add(home_user)
        return HomeUserAddResponse(
            username=target_user.username, home_name=home.name, user_type=user_type
        )

    async def user_can_access(self, user_id: int, home_id: int) -> bool:
        return await self.repo.user_has_access(user_id, home_id)
