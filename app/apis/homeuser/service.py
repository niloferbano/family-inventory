# app/apis/homeuser/service.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.homeuser.repository import HomeUserRepository
from app.apis.homeuser.models import HomeUser, UserType
from app.apis.users.models import User


class HomeUserService:

    def __init__(self, session: AsyncSession, current_user: User):
        self.repo = HomeUserRepository(session)
        self.current_user = current_user
        
    async def create_owner_for_home(self, home_id: int) -> HomeUser:
        existing = await self.repo.get(self.current_user.id, home_id)
        if existing:
            return existing

        home_user = HomeUser(
            user_id=self.current_user.id,
            home_id=home_id,
            user_type=UserType.HOME_OWNER,
        )
        return await self.repo.add(home_user)

    async def add_user_to_home(
        self,
        home_id: int,
        target_user_id: int,
        user_type: UserType,
    ) -> HomeUser:
        
        if user_type == UserType.HOME_OWNER:
            raise ValueError("Owners can only be created during home creation.")

        is_owner = await self.repo.user_is_owner(self.current_user.id, home_id)

        if not (self.current_user.is_admin or is_owner):
            raise PermissionError("Not allowed to add users to this home.")

        existing = await self.repo.get(target_user_id, home_id)
        if existing:
            raise ValueError("User already assigned to this home.")

        home_user = HomeUser(
            user_id=target_user_id,
            home_id=home_id,
            user_type=user_type,
        )

        return await self.repo.add(home_user)

    async def user_can_access(self, user_id: int, home_id: int) -> bool:
        return await self.repo.user_has_access(user_id, home_id)
    
    async def user_has_any_home(self, user_id: int) -> bool:
        return await self.repo.user_has_any_home(user_id=user_id)

    async def user_is_owner_anywhere(self, user_id: int) -> bool:
        return await self.repo.user_is_owner_anywhere(user_id=user_id)
    