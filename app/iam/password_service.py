from app.apis.users.utils import hash_password as _hash
from app.apis.users.utils import verify_password as _verify
from app.iam.types import HashedString


class PasswordService:
    @staticmethod
    def hash(password: str) -> str:
        return _hash(password)

    @staticmethod
    def verify(password: str, hashed_password: HashedString) -> bool:
        return _verify(password, hashed_password)
