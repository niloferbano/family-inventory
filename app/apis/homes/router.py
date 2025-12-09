
from typing import Annotated
from fastapi import APIRouter, Depends
from app.apis.homes.schema import HomeCreate, HomeRead
from app.apis.homes.service import HomeService
from app.core.database.session import get_session
from app.iam.dependencies import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/homes", tags=["homes"])
SessionDep = Annotated[AsyncSession, Depends(get_session)] 

@router.post("/", response_model=HomeRead)
async def create_home(
    data: HomeCreate,
    session: SessionDep,
    current_user=Depends(get_current_user),
):
        service = HomeService(session, current_user)
        return await service.create_home(data)


@router.get("/{home_id}", response_model=HomeRead)
async def get_home(
    home_id: int,
    session=Depends(get_session),
    user=Depends(get_current_user),
):
    service = HomeService(session, user)
    return await service.get_home_for_user(home_id)