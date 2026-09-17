from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.apis.users.auth_service import AuthService
from app.apis.users.exceptions import (InvalidActivationToken,
                                       InvalidCredentials, InvalidResetToken,
                                       UserAlreadyActive, UserAlreadyExists,
                                       UserNameAlreadyExists)
from app.apis.users.schema import (PaginatedUsersResponse,
                                   PasswordResetConfirm, PasswordResetRequest,
                                   ResendActivationResponse,
                                   UserActivationRequest, UserBase,
                                   UserRegisterResponse)
from app.apis.users.user_service import UserService
from app.core.database.pagination import PaginationParams, get_pagination
from app.core.database.session import DBManager, get_db
from app.core.logging import get_logger
from app.iam.dependencies import get_current_user
from app.iam.permissions import PermissionsValidator
from app.iam.schema import TokenResponse
from app.iam.types import ActivationKey

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user


@router.post("/register", status_code=status.HTTP_200_OK)
async def register_user(
    user_input: UserBase,
    db_manager=Depends(get_db),
) -> UserRegisterResponse:
    async with db_manager.begin() as session:
        try:
            return await UserService(session).register_user(user_data=user_input)
        except UserNameAlreadyExists as exc:
            raise HTTPException(
                status_code=409,
                detail="Username is unavailable. Please choose another username.",
            ) from exc
        except UserAlreadyExists as exc:
            raise HTTPException(
                status_code=409,
                detail="User already exists",
            ) from exc


@router.get(path="/activate/{key}", status_code=status.HTTP_200_OK)
async def check_activation_key(key: str, db_manager=Depends(get_db)):
    async with db_manager.begin() as session:
        user_service = UserService(session=session)
        try:
            await user_service.validate_activation_link(key)
        except InvalidActivationToken:
            raise HTTPException(
                status_code=400, detail="Invalid or expired activation link"
            )
        except UserAlreadyActive:
            raise HTTPException(status_code=400, detail="ALREADY_ACTIVE")
        return {"message": "Activation key is valid"}


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
        except InvalidActivationToken:
            raise HTTPException(
                status_code=400, detail="Invalid or expired activation link"
            )
        except UserAlreadyExists:
            raise HTTPException(status_code=409, detail="User already exists.")
        except UserNameAlreadyExists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="User name already exists"
            )


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, db_manager=Depends(get_db)):
    async with db_manager.begin() as session:
        service = AuthService(session=session)
        try:
            content_type = request.headers.get("content-type", "")
            if (
                "application/x-www-form-urlencoded" in content_type
                or "multipart/form-data" in content_type
            ):
                form = await request.form()
                email = form.get("username") or form.get("email")
                password = form.get("password")
            else:
                data = await request.json()
                email = data.get("email") or data.get("username")
                password = data.get("password")

            if not email or not password:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Missing email/username or password",
                )

            return await service.login(str(email), str(password))
        except InvalidCredentials:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid credentials"
            )


@router.get(
    "/",
    dependencies=[Depends(PermissionsValidator(require_admin=True))],
    response_model=PaginatedUsersResponse,
    summary="Get all users (Admin only)",
)
async def get_all_users(
    request: Request,
    pagination_params: PaginationParams = Depends(),
    db_manager: DBManager = Depends(get_db),
):
    pagination = get_pagination(
        page=pagination_params.page,
        page_size=pagination_params.page_size,
    )

    async with db_manager.begin() as session:
        service = UserService(session)
        return await service.get_all_users(
            pagination=pagination,
            request_url=str(request.url),
        )


@router.post("/password-reset/request")
async def request_password_reset(
    payload: PasswordResetRequest, db_manager=Depends(get_db)
):
    async with db_manager.begin() as session:
        await AuthService(session).request_password_reset(str(payload.email))
    return {
        "message": "If an eligible account exists, a password reset email will be sent."
    }


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    payload: PasswordResetConfirm, db_manager=Depends(get_db)
):
    try:
        async with db_manager.begin() as session:
            await AuthService(session).reset_password(
                payload.token.get_secret_value(), payload.password.get_secret_value()
            )
    except InvalidResetToken:
        raise HTTPException(
            status_code=400, detail="Invalid or expired password reset token"
        )
    logger.info("password_reset_completed")
    return {"message": "Password reset successfully. Log in with your new password."}


@router.post("/resend-activation")
async def resend_activation(
    payload: PasswordResetRequest, db_manager=Depends(get_db)
) -> ResendActivationResponse:
    async with db_manager.begin() as session:
        response = await UserService(session).resend_activation(payload.email)
    logger.info("activation_resend_completed")
    return response
