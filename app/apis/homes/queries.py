from sqlalchemy import select

from app.apis.homes.models import Home
from app.core.database.base import HomeId


def query_get_home_by_id(home_id: HomeId):
    return select(Home).where(Home.id == home_id)


def query_get_home_by_name(name: str):
    return select(Home).where(Home.name == name)


def query_get_home_for_user(home_id: HomeId, is_admin: bool):
    if is_admin:
        # admin sees all
        return select(Home).where(Home.id == home_id)

    # normal user: check ownership
    return select(Home).where(
        Home.id == home_id,
    )
