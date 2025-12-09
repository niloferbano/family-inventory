from fastapi import APIRouter, Depends, HTTPException, status

from app.apis.homes.exceptions import HomeAlreadyExists
from app.apis.homes.schema import HomeCreate, HomeRead
from app.apis.homes.service import HomeService
from app.core.database.session import get_db
from app.iam.dependencies import get_current_user

router = APIRouter(prefix="/homes", tags=["homes"])


@router.post("/", response_model=HomeRead)
async def create_home(
    data: HomeCreate,
    db_manager=Depends(get_db),
    current_user=Depends(get_current_user),
):
    async with db_manager.begin() as session:
        try:
            service = HomeService(session, current_user)
            return await service.create_home(data)
        except HomeAlreadyExists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Home with this name already exists",
            )


@router.get("/{home_id}", response_model=HomeRead)
async def get_home(
    home_id: int,
    db_manager=Depends(get_db),
    user=Depends(get_current_user),
):
    async with db_manager.begin() as session:
        service = HomeService(session, user)
        return await service.get_home_for_user(home_id)
