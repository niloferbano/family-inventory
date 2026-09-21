from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.apis.homes.models import Home
from app.apis.homeuser.models import HomeUser, UserType
from app.apis.homeuser.repository import HomeUserRepository
from app.apis.homeuser.schema import ChangeHomeUserRoleRequest, HomeUserAddRequest
from app.apis.homeuser.service import HomeUserService
from app.apis.household_categories.models import HouseholdCategory
from app.apis.household_categories.schemas import HouseholdCategoryCreate
from app.apis.inventory.models import InventoryItem
from app.core.database.base import HomeId, UserId
from app.core.database.session import get_db
from app.iam.dependencies import get_current_user

router = APIRouter(prefix="/homes/{home_id}/settings", tags=["Home settings"])


class HomeNameUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


async def managed_home(
    home_id: HomeId, db=Depends(get_db), user=Depends(get_current_user)
):
    async with db.begin() as session:
        # Serialize settings writes for a home, including membership changes.
        home = await session.scalar(
            select(Home).where(Home.id == home_id).with_for_update()
        )
        membership = await HomeUserRepository(session).get(user.id, home_id)
        if not membership or not (
            membership.user_type == UserType.OWNER or user.is_admin
        ):
            raise HTTPException(403, "You do not have permission to manage this home.")
        if home is None:
            raise HTTPException(404, "Home not found.")
        yield session, user, home


@router.get("")
async def get_settings(context=Depends(managed_home)):
    session, user, home = context
    members = await HomeUserRepository(session).list_members_with_users(home.id)
    categories = (
        await session.execute(
            select(HouseholdCategory, func.count(InventoryItem.id))
            .outerjoin(
                InventoryItem,
                InventoryItem.household_category_id == HouseholdCategory.id,
            )
            .where(HouseholdCategory.home_id == home.id)
            .group_by(HouseholdCategory.id)
            .order_by(HouseholdCategory.name)
        )
    ).all()
    return {
        "home_id": home.id,
        "name": home.name,
        "members": [
            {
                "user_id": member.id,
                "username": member.username,
                "email": member.email,
                "user_type": role,
            }
            for member, role in members
        ],
        "categories": [
            {"id": c.id, "name": c.name, "item_count": count} for c, count in categories
        ],
    }


@router.patch("")
async def rename_home(payload: HomeNameUpdate, context=Depends(managed_home)):
    session, user, home = context
    try:
        async with session.begin_nested():
            home.name = payload.name
            await session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) != "23505":
            raise
        raise HTTPException(409, "A home with this name already exists.") from exc
    return {"home_id": home.id, "name": home.name}


@router.post("/members", status_code=201)
async def add_member(payload: HomeUserAddRequest, context=Depends(managed_home)):
    session, user, home = context
    return await HomeUserService(session, user).add_user_to_home(
        home.id, payload.user_email, payload.user_type
    )


async def editable_member(session, home_id, user_id):
    member = await session.scalar(
        select(HomeUser)
        .where(HomeUser.home_id == home_id, HomeUser.user_id == user_id)
        .with_for_update()
    )
    if member is None:
        raise HTTPException(404, "Member not found in this home.")
    if member.user_type == UserType.OWNER:
        raise HTTPException(
            409, "Home owners cannot be removed or demoted in settings."
        )
    return member


@router.patch("/members/{user_id}", status_code=204)
async def change_member(
    user_id: UserId, payload: ChangeHomeUserRoleRequest, context=Depends(managed_home)
):
    session, user, home = context
    if payload.user_type == UserType.OWNER:
        raise HTTPException(422, "Choose resident or guest.")
    member = await editable_member(session, home.id, user_id)
    member.user_type = payload.user_type
    await session.flush()


@router.delete("/members/{user_id}", status_code=204)
async def remove_member(user_id: UserId, context=Depends(managed_home)):
    session, user, home = context
    member = await editable_member(session, home.id, user_id)
    await session.delete(member)
    await session.flush()


async def home_category(session, home_id, category_id):
    category = await session.scalar(
        select(HouseholdCategory)
        .where(
            HouseholdCategory.id == category_id, HouseholdCategory.home_id == home_id
        )
        .with_for_update()
    )
    if category is None:
        raise HTTPException(404, "Category not found in this home.")
    return category


@router.patch("/categories/{category_id}")
async def rename_category(
    category_id: UUID, payload: HouseholdCategoryCreate, context=Depends(managed_home)
):
    session, user, home = context
    category = await home_category(session, home.id, category_id)
    try:
        async with session.begin_nested():
            category.name = payload.name
            await session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) != "23505":
            raise
        raise HTTPException(
            409, "A category with this name already exists in this home."
        ) from exc
    return {"id": category.id, "name": category.name}


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: UUID, context=Depends(managed_home)):
    session, user, home = context
    category = await home_category(session, home.id, category_id)
    try:
        async with session.begin_nested():
            await session.delete(category)
            await session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) != "23503":
            raise
        raise HTTPException(
            409,
            "Move this category's inventory items to another category before deleting.",
        ) from exc
