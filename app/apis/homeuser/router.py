# app/apis/homeuser/router.py
from fastapi import APIRouter, Depends, HTTPException

from app.apis.homeuser.exceptions import (AlreadyMemberException,
                                          TargetUserDoesnotExists)
from app.apis.homeuser.schema import HomeUserAddRequest, HomeUserAddResponse
from app.apis.homeuser.service import HomeUserService
from app.core.database.session import get_db
from app.iam.dependencies import get_current_user

router = APIRouter(prefix="/homeuser", tags=["Home User"])


@router.post("/{home_id}/users", response_model=HomeUserAddResponse)
async def add_user_to_home(
    home_id: int,
    payload: HomeUserAddRequest,
    db_manager=Depends(get_db),
    current_user=Depends(get_current_user),
):
    async with db_manager.begin() as session:
        service = HomeUserService(session, current_user)
        try:
            return await service.add_user_to_home(
                home_id=home_id,
                target_user_email=payload.user_email,
                user_type=payload.user_type,
            )
        except AlreadyMemberException as exec:
            raise HTTPException(status_code=exec.status_code, detail=exec.detail)
        except TargetUserDoesnotExists as exec:
            raise HTTPException(status_code=exec.status_code, detail=exec.detail)
