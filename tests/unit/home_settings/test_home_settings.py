from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.apis.homes.models import Home
from app.apis.homeuser.models import HomeUser, UserType
from app.apis.household_categories.models import HouseholdCategory
from app.apis.inventory.models import InventoryItem
from app.apis.product.models import Product
from app.apis.users.models import User


@pytest_asyncio.fixture
async def data(db_session, auth_headers):
    owner = await db_session.scalar(
        select(User).where(User.email == "auth@example.com")
    )
    home, other = Home(name="Settings home"), Home(name="Other home")
    member = User(
        username="member",
        email="member@example.com",
        hashed_password="unused",
        is_active=True,
    )
    db_session.add_all([home, other, member])
    await db_session.flush()
    link = HomeUser(home_id=home.id, user_id=owner.id, user_type=UserType.OWNER)
    db_session.add_all(
        [
            link,
            HomeUser(home_id=other.id, user_id=member.id, user_type=UserType.RESIDENCE),
        ]
    )
    category = HouseholdCategory(home_id=home.id, name="Kitchen")
    foreign = HouseholdCategory(home_id=other.id, name="Foreign")
    db_session.add_all([category, foreign])
    await db_session.commit()
    return home, other, owner, member, link, category, foreign


ACTIONS = [
    ("GET", "", None),
    ("PATCH", "", {"name": "Changed"}),
    ("POST", "/members", {"user_email": "member@example.com", "user_type": "guest"}),
    ("PATCH", "/members/{member}", {"user_type": "guest"}),
    ("DELETE", "/members/{member}", None),
    ("PATCH", "/categories/{category}", {"name": "Changed"}),
    ("DELETE", "/categories/{category}", None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", ACTIONS)
@pytest.mark.parametrize(
    "access", ["anonymous", "nonmember", "resident", "guest", "outside_admin"]
)
async def test_permissions(
    client, db_session, auth_headers, data, method, path, payload, access
):
    home, _, owner, _, link, category, _ = data
    if access in ("nonmember", "outside_admin"):
        await db_session.delete(link)
    elif access in ("resident", "guest"):
        link.user_type = UserType.RESIDENCE if access == "resident" else UserType.GUEST
    owner.is_admin = access == "outside_admin"
    await db_session.commit()
    response = await client.request(
        method,
        f"/homes/{home.id}/settings"
        + path.format(member=owner.id, category=category.id),
        headers={} if access == "anonymous" else auth_headers,
        **({"json": payload} if payload else {}),
    )
    assert response.status_code == (401 if access == "anonymous" else 403)
    await db_session.refresh(home)
    await db_session.refresh(category)
    assert home.name == "Settings home"
    assert category.name == "Kitchen"


@pytest.mark.asyncio
@pytest.mark.parametrize("admin", [False, True])
async def test_read_and_rename(client, db_session, auth_headers, data, admin):
    home, _, owner, _, link, category, _ = data
    if admin:
        owner.is_admin = True
        link.user_type = UserType.RESIDENCE
        await db_session.commit()
    url = f"/homes/{home.id}/settings"
    response = await client.get(url, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["members"][0]["user_id"] == str(owner.id)
    assert response.json()["categories"] == [
        {"id": str(category.id), "name": "Kitchen", "item_count": 0}
    ]
    response = await client.patch(
        url, headers=auth_headers, json={"name": "  Updated home  "}
    )
    assert response.status_code == 200
    await db_session.refresh(home)
    assert home.name == "Updated home"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,status", [("  ", 422), ("a", 422), ("x" * 101, 422), ("Other home", 409)]
)
async def test_name_errors(client, db_session, auth_headers, data, name, status):
    home = data[0]
    response = await client.patch(
        f"/homes/{home.id}/settings", headers=auth_headers, json={"name": name}
    )
    assert response.status_code == status
    await db_session.refresh(home)
    assert home.name == "Settings home"


@pytest.mark.asyncio
async def test_member_lifecycle(client, db_session, auth_headers, data):
    home, other, owner, member, _, _, _ = data
    url = f"/homes/{home.id}/settings/members"
    # A member of another home is not editable in this one.
    assert (
        await client.patch(
            f"{url}/{member.id}", headers=auth_headers, json={"user_type": "guest"}
        )
    ).status_code == 404
    payload = {"user_email": member.email, "user_type": "residence"}
    assert (
        await client.post(url, headers=auth_headers, json=payload)
    ).status_code == 201
    assert (
        await client.post(url, headers=auth_headers, json=payload)
    ).status_code == 409
    assert (
        await client.patch(
            f"{url}/{member.id}", headers=auth_headers, json={"user_type": "guest"}
        )
    ).status_code == 204
    link = await db_session.scalar(
        select(HomeUser).where(
            HomeUser.home_id == home.id, HomeUser.user_id == member.id
        )
    )
    assert link.user_type == UserType.GUEST
    assert (
        await client.patch(
            f"{url}/{member.id}", headers=auth_headers, json={"user_type": "owner"}
        )
    ).status_code == 422
    assert (
        await client.patch(
            f"{url}/{owner.id}", headers=auth_headers, json={"user_type": "guest"}
        )
    ).status_code == 409
    assert (
        await client.delete(f"{url}/{owner.id}", headers=auth_headers)
    ).status_code == 409
    assert (
        await client.delete(f"{url}/{member.id}", headers=auth_headers)
    ).status_code == 204
    assert (
        await db_session.scalar(
            select(HomeUser).where(
                HomeUser.home_id == home.id, HomeUser.user_id == member.id
            )
        )
        is None
    )
    assert (
        await db_session.scalar(
            select(HomeUser).where(
                HomeUser.home_id == other.id, HomeUser.user_id == member.id
            )
        )
        is not None
    )
    assert (
        await client.delete(f"{url}/{uuid4()}", headers=auth_headers)
    ).status_code == 404
    assert (
        await client.post(
            url,
            headers=auth_headers,
            json={"user_email": "missing@example.com", "user_type": "guest"},
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_category_lifecycle(client, db_session, auth_headers, data):
    home, _, _, _, _, category, foreign = data
    url = f"/homes/{home.id}/settings/categories"
    for method in ("PATCH", "DELETE"):
        response = await client.request(
            method,
            f"{url}/{foreign.id}",
            headers=auth_headers,
            **({"json": {"name": "Other"}} if method == "PATCH" else {}),
        )
        assert response.status_code == 404
    for name in (" ", "x" * 61):
        assert (
            await client.patch(
                f"{url}/{category.id}", headers=auth_headers, json={"name": name}
            )
        ).status_code == 422
    response = await client.post(
        f"/homes/{home.id}/categories", headers=auth_headers, json={"name": "Second"}
    )
    assert response.status_code == 201
    second = response.json()["id"]
    assert (
        await client.patch(
            f"{url}/{category.id}", headers=auth_headers, json={"name": "Second"}
        )
    ).status_code == 409
    assert (
        await client.patch(
            f"{url}/{category.id}", headers=auth_headers, json={"name": " Food "}
        )
    ).status_code == 200
    await db_session.refresh(category)
    assert category.name == "Food"
    product = Product(name="Milk")
    db_session.add(product)
    await db_session.flush()
    item = InventoryItem(
        home_id=home.id, product_id=product.id, household_category_id=category.id
    )
    db_session.add(item)
    await db_session.commit()
    response = await client.get(f"/homes/{home.id}/settings", headers=auth_headers)
    counts = {c["id"]: c["item_count"] for c in response.json()["categories"]}
    assert counts == {str(category.id): 1, second: 0}
    response = await client.delete(f"{url}/{category.id}", headers=auth_headers)
    assert response.status_code == 409
    assert "Move" in response.json()["detail"]
    await db_session.refresh(category)
    await db_session.refresh(item)
    assert item.household_category_id == category.id
    assert (
        await client.delete(f"{url}/{second}", headers=auth_headers)
    ).status_code == 204
    assert await db_session.get(HouseholdCategory, UUID(second)) is None
