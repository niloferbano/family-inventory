from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.apis.inventory.schema import (InventoryCreateRequest,
                                       InventoryCreateResponse,
                                       PaginatedInventorytItemResponse)
from app.apis.inventory.service import InventoryService
from app.core.database.base import HomeId
from app.core.database.pagination import PaginationParams, get_pagination
from app.core.database.session import get_db
from app.iam.dependencies import get_current_user

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.post("/{home_id}", response_model=list[InventoryCreateResponse])
async def add_inventory_item(
    home_id: HomeId,
    payload: list[InventoryCreateRequest],
    db_manager=Depends(get_db),
    current_user=Depends(get_current_user),
):
    async with db_manager.begin() as session:
        service = InventoryService(session, current_user)
        return await service.add_items(home_id, payload)


@router.get("/{home_id}", response_model=PaginatedInventorytItemResponse)
async def list_inventory_items(
    home_id: HomeId,
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
        service = InventoryService(session, current_user)
        try:
            return await service.get_items(
                home_id=home_id, pagination=pagination, request_url=request.url
            )
        except PermissionError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User doesn't have access",
            )
