from pydantic import EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.homes.exceptions import HomeNotFound
from app.apis.homes.repository import HomeRepository
from app.apis.homeuser.exceptions import (AlreadyMemberException,
                                          HomePermissionDenied,
                                          OwnerAssignmentNotAllowed,
                                          TargetUserDoesNotExist)
from app.apis.homeuser.models import HomeUser, UserType
from app.apis.homeuser.repository import HomeUserRepository
from app.apis.homeuser.schema import HomeUserAddResponse
from app.apis.users.models import User
from app.apis.users.repository import UserRepository
from app.core.database.base import HomeId


class HomeUserService:

    def __init__(self, session: AsyncSession, current_user: User):
        self.repo = HomeUserRepository(session)
        self.user_repo = UserRepository(session)
        self.home_repo = HomeRepository(session)
        self.current_user = current_user
        self.session = session

    async def create_owner_for_home(self, home_id: HomeId) -> HomeUser:
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
        home_id: HomeId,
        target_user_email: EmailStr,
        user_type: UserType,
    ) -> HomeUserAddResponse:

        if user_type == UserType.OWNER:
            raise OwnerAssignmentNotAllowed()

        home = await self.home_repo.get_by_id(home_id=home_id)
        if not home:
            raise HomeNotFound(home_id)

        target_user = await self.user_repo.get_by_email(email=target_user_email)
        if not target_user:
            raise TargetUserDoesNotExist(target_user_email)

        is_owner = await self.repo.user_is_owner(self.current_user.id, home_id)

        if not (self.current_user.is_admin or is_owner):
            raise HomePermissionDenied(home_id=home_id)

        home_user = HomeUser(
            user_id=target_user.id,
            home_id=home_id,
            user_type=user_type,
        )
        try:
            await self.repo.add(home_user)
        except IntegrityError as exc:
            await self.session.rollback()
            raise AlreadyMemberException(home_id, target_user.id) from exc

        return HomeUserAddResponse(
            username=target_user.username,
            home_name=home.name,
            user_type=user_type,
        )

    async def user_can_access(self, user_id: int, home_id: HomeId) -> bool:
        return await self.repo.user_has_access(user_id, home_id)
