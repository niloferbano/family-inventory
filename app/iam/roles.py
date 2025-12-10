from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    HOME_OWNER = "home_owner"
    RESIDENT = "resident"
    GUEST = "guest"
