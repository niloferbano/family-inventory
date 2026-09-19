from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.homeuser.repository import HomeUserRepository
from app.apis.household_categories.models import HouseholdCategory
from app.apis.household_categories.repository import HouseholdCategoryRepository
from app.apis.household_categories.schemas import HouseholdCategoryCreate
from app.apis.inventory.exceptions import InventoryAccessDenied
from app.apis.users.models import User
from app.core.database.base import HomeId


class HouseholdCategoryService:
    """Home-scoped category operations."""

    def __init__(self, session: AsyncSession, current_user: User):
        self.session = session
        self.current_user = current_user
        self.repo = HouseholdCategoryRepository(session)

    async def create_category(
        self, *, home_id: HomeId, data: HouseholdCategoryCreate
    ) -> HouseholdCategory:
        memberships = HomeUserRepository(self.session)
        owner = await memberships.user_is_owner(self.current_user.id, home_id)
        member_admin = self.current_user.is_admin and await memberships.user_has_access(
            self.current_user.id, home_id
        )
        if not (owner or member_admin):
            raise InventoryAccessDenied(home_id=str(home_id))
        return await self.repo.create(
            HouseholdCategory(id=uuid4(), home_id=home_id, name=data.name)
        )

    async def list_categories(self, *, home_id: HomeId) -> list[HouseholdCategory]:
        return await self.repo.list_by_home(home_id)
