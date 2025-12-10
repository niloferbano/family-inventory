from fastapi import APIRouter, Depends, HTTPException, status

from app.apis.users.auth_service import AuthService
from app.apis.users.exceptions import UserAlreadyExists, UserNameAlreadyExists
from app.apis.users.schema import (UserActivationRequest, UserBase, UserLogin,
                                   UserRegisterResponse)
from app.apis.users.user_service import UserService
from app.core.database.session import get_db
from app.iam.dependencies import get_current_user
from app.iam.schema import TokenResponse
from app.iam.types import ActivationKey

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user


@router.post("/register", status_code=status.HTTP_200_OK)
async def register_user(
    user_input: UserBase,
    db_manager=Depends(get_db),
) -> UserRegisterResponse | None:
    async with db_manager.begin() as session:
        user_service = UserService(session)
        try:
            return await user_service.register_user(user_data=user_input)
        except UserAlreadyExists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str("User already exists.")
            )
        except (
            Exception
        ) as exc:  # pragma: no cover - FastAPI will format error response
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc


@router.post(path="/activate/{key}", status_code=status.HTTP_201_CREATED)
async def activate_user(
    key: ActivationKey, payload: UserActivationRequest, db_manager=Depends(get_db)
):
    async with db_manager.begin() as session:
        user_service = UserService(session)
        try:
            await user_service.create_user(
                activation_key=key,
                user_input=payload,
            )

            return {"message": "User activated successfully"}
        except UserNameAlreadyExists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="User name already exists"
            )


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db_manager=Depends(get_db)):
    async with db_manager.begin() as session:
        service = AuthService(session=session)
        return await service.login(payload.email, payload.password)
