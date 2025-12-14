from app.apis.homeuser.models import UserType
from app.core.database.error_codes import ErrorCode
from app.core.database.exceptions import (
    DomainConflictError,
    DomainNotFoundError,
    DomainPermissionError,
)


class AlreadyMemberException(DomainConflictError):
    def __init__(self, home_id, user_id):
        super().__init__(
            code=ErrorCode.HOME_USER_ALREADY_MEMBER,
            message="User is already a member of this home",
            details={
                "home_id": str(home_id),
                "user_id": user_id,
            },
        )


class TargetUserDoesNotExist(DomainNotFoundError):
    def __init__(self, email: str):
        super().__init__(
            code=ErrorCode.TARGET_USER_NOT_FOUND,
            message="Target user does not exist",
            details={"email": email},
        )


class OwnerAssignmentNotAllowed(DomainConflictError):
    def __init__(self):
        super().__init__(
            code=ErrorCode.OWNER_ASSIGNMENT_NOT_ALLOWED,
            message="Owners can only be assigned during home creation",
            details={
                "allowed_roles": [
                    UserType.RESIDENCE.value,
                    UserType.GUEST.value,
                ]
            },
        )


class HomePermissionDenied(DomainPermissionError):
    def __init__(self, home_id):
        super().__init__(
            code=ErrorCode.HOME_PERMISSION_DENIED,
            message="You are not allowed to access this home",
            details={"home_id": str(home_id)},
        )