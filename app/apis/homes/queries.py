from sqlalchemy import select

from app.apis.homes.models import Home
from app.apis.homeuser.models import HomeUser
from app.core.database.base import HomeId, UserId


def query_get_home_by_id(home_id: HomeId):
    return select(Home).where(Home.id == home_id)


def query_get_home_by_name(name: str):
    return select(Home).where(Home.name == name)


def query_get_home_for_user(home_id: HomeId, user_id: UserId, is_admin: bool):
    if is_admin:
        # admin sees all
        return select(Home).where(Home.id == home_id)

    # normal user: must be a member of the home
    return (
        select(Home)
        .join(HomeUser, HomeUser.home_id == Home.id)
        .where(Home.id == home_id, HomeUser.user_id == user_id)
    )
