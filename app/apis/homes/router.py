from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.apis.homes.schema import (GetHomeWithMembersResponse, HomeCreate,
                                   HomeRead, PaginatedAdminHomesResponse)
from app.apis.homes.service import HomeService
from app.core.database.base import HomeId
from app.core.database.exceptions import DomainPermissionError
from app.core.database.pagination import PaginationParams, get_pagination
from app.core.database.session import get_db
from app.iam.dependencies import get_current_user
from app.iam.permissions import PermissionsValidator

router = APIRouter(prefix="/homes", tags=["homes"])


@router.post("/", response_model=HomeRead)
async def create_home(
    data: HomeCreate,
    db_manager=Depends(get_db),
    current_user=Depends(get_current_user),
):
    async with db_manager.begin() as session:
        service = HomeService(session, current_user)
        return await service.create_home(data)


@router.get("/{home_id}", response_model=HomeRead)
async def get_home(
    home_id: HomeId,
    db_manager=Depends(get_db),
    user=Depends(get_current_user),
):
    async with db_manager.begin() as session:
        service = HomeService(session, user)
        return await service.get_home_for_user(home_id)


@router.get("/", response_model=list[GetHomeWithMembersResponse])
async def get_homes(
    db_manager=Depends(get_db),
    user=Depends(get_current_user),
):
    async with db_manager.begin() as session:
        service = HomeService(session, user)
        return await service.get_all_homes_for_user()


@router.get(
    "/admin/homes",
    dependencies=[Depends(PermissionsValidator(require_admin=True))],
    response_model=PaginatedAdminHomesResponse,
    summary="Admin: Get all homes with members",
)
async def admin_get_all_homes(
    request: Request,
    pagination_params: PaginationParams = Depends(),
    db_manager=Depends(get_db),
    current_user=Depends(get_current_user),
):
    pagination = get_pagination(
        page=pagination_params.page,
        page_size=pagination_params.page_size,
    )
    async with db_manager.begin() as session:
        service = HomeService(session, current_user=current_user)
        return await service.get_all_homes_admin(
            pagination=pagination, request_url=str(request.url)
        )


@router.delete("/{home_id}", status_code=204)
async def delete_home(
    home_id: HomeId,
    db_manager=Depends(get_db),
    current_user=Depends(get_current_user),
):
    async with db_manager.begin() as session:
        service = HomeService(session, current_user)
        try:
            await service.delete_home(home_id)
        except DomainPermissionError:
            return HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this home",
            )
