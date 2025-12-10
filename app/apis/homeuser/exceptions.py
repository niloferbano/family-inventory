# app/apis/homeuser/exceptions.py
from fastapi import HTTPException, status


class AlreadyMemberException(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already assigned to this home.",
        )


class ForbiddenHomeAccess(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this home.",
        )


class TargetUserDoesnotExists(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target user doesn't exist",
        )
