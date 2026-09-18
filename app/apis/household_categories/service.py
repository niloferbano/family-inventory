from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.household_categories.models import HouseholdCategory
from app.apis.household_categories.repository import HouseholdCategoryRepository
from app.apis.household_categories.schemas import HouseholdCategoryCreate
from app.apis.users.models import User
from app.core.database.base import HomeId


class HouseholdCategoryService:
    """Thin service layer over HouseholdCategoryRepository.

    No router wired up yet (issue #43 scope is model + relationship only) —
    this exists so a future API layer has a stable place to add home
    membership/permission checks without touching the repository.
    """

    def __init__(self, session: AsyncSession, current_user: User):
        self.session = session
        self.current_user = current_user
        self.repo = HouseholdCategoryRepository(session)

    async def create_category(
        self, *, home_id: HomeId, data: HouseholdCategoryCreate
    ) -> HouseholdCategory:
        return await self.repo.create(
            HouseholdCategory(id=uuid4(), home_id=home_id, name=data.name)
        )

    async def list_categories(self, *, home_id: HomeId) -> list[HouseholdCategory]:
        return await self.repo.list_by_home(home_id)
