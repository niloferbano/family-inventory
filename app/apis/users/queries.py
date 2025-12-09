import sqlalchemy as sa

from .models import User


def get_user_by_email_query(email: str):
    return sa.select(User).where(User.email == email)


def count_active_users_query():
    return sa.select(sa.func.count()).select_from(User).where(User.is_active)
