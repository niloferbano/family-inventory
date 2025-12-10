from fastapi import Depends, HTTPException, status

from app.apis.users.models import User
from app.iam.dependencies import get_current_user


class PermissionsValidator:
    def __init__(self, require_admin: bool = False):
        self.require_admin = require_admin

    async def __call__(self, user: User = Depends(get_current_user)) -> None:

        if self.require_admin and not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied",
            )
