from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    # 1. Encode UTF-8
    password_bytes = password.encode("utf-8")
    # 2. Truncate to 72 bytes
    truncated = password_bytes[:72]
    # 3. Decode back to UTF-8 string (ignore partial multibyte chars)
    safe_password = truncated.decode("utf-8", errors="ignore")
    # 4. Now hash the SAFE STRING
    return pwd_context.hash(safe_password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Check a plain password against the stored hash."""
    return pwd_context.verify(password, hashed_password)
