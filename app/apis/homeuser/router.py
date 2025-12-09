# app/apis/homeuser/router.py
from fastapi import APIRouter, Depends

from app.apis.users.router import SessionDep
from app.apis.homeuser.schema import HomeUserAddRequest, HomeUserRead
from app.apis.homeuser.service import HomeUserService
from app.iam.dependencies import get_current_user

router = APIRouter(prefix="/homeuser", tags=["Home User"])


@router.post("/{home_id}/users", response_model=HomeUserRead)
async def add_user_to_home(
    home_id: int,
    payload: HomeUserAddRequest,  # only user_id + type
    session: SessionDep,
    current_user=Depends(get_current_user),
):
    service = HomeUserService(session, current_user)
    return await service.add_user_to_home(
        home_id=home_id,
        target_user_id=payload.user_id,
        user_type=payload.user_type,
    )