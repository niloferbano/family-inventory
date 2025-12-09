from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from jose import ExpiredSignatureError, JWTError

from app.apis.users.exceptions import InvalidCredentials
from app.iam.token_service import TokenService
from app.core.database.session import get_session
from app.apis.users.repository import UserRepository


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session=Depends(get_session)
):
    try:
        payload = TokenService.decode_token(token)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise InvalidCredentials()

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(int(user_id))

    if not user:
        raise InvalidCredentials()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active",
        )

    return user