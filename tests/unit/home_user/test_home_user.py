import pytest

from app.apis.homes.models import Home
from app.apis.homeuser.models import HomeUser, UserType
from app.apis.users.models import User


async def _create_user(mock_db, username: str, email: str, is_admin: bool = False):
    async with mock_db.sessionmaker() as session:
        user = User(
            username=username,
            email=email,
            hashed_password="hashed",
            is_active=True,
            is_admin=is_admin,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.mark.asyncio
async def test_owner_can_add_user_to_home(
    client,
    auth_headers,
    mock_db,
):
    # Create home
    home = await client.post(
        "/homes/",
        json={"name": "Owner Home"},
        headers=auth_headers,
    )
    home_id = home.json()["id"]

    # Create second user directly in DB
    from app.apis.users.models import User

    async with mock_db.sessionmaker() as session:
        user = User(
            username="resident",
            email="resident@example.com",
            hashed_password="hashed",
            is_active=True,
            is_admin=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    # Add user as resident
    res = await client.post(
        f"/homeuser/{home_id}/users",
        json={
            "user_email": user.email,
            "user_type": "residence",
        },
        headers=auth_headers,
    )

    assert res.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_member_returns_error(
    client,
    auth_headers,
    mock_db,
):
    home = await client.post(
        "/homes/",
        json={"name": "Dup Home"},
        headers=auth_headers,
    )
    home_id = home.json()["id"]

    target_user = await _create_user(mock_db, "resident", "resident@example.com")

    first = await client.post(
        f"/homeuser/{home_id}/users",
        json={"user_email": target_user.email, "user_type": "residence"},
        headers=auth_headers,
    )
    assert first.status_code == 200

    second = await client.post(
        f"/homeuser/{home_id}/users",
        json={"user_email": target_user.email, "user_type": "residence"},
        headers=auth_headers,
    )

    assert second.status_code == 409
    body = second.json()
    assert body["error"] == "HOME_USER_ALREADY_MEMBER"
    assert body["details"]["home_id"] == home_id
    assert body["details"]["user_id"] == str(target_user.id)


@pytest.mark.asyncio
async def test_target_user_not_found_returns_error(
    client,
    auth_headers,
):
    home = await client.post(
        "/homes/",
        json={"name": "Missing User Home"},
        headers=auth_headers,
    )
    home_id = home.json()["id"]

    res = await client.post(
        f"/homeuser/{home_id}/users",
        json={"user_email": "nobody@example.com", "user_type": "guest"},
        headers=auth_headers,
    )

    assert res.status_code == 404
    body = res.json()
    assert body["error"] == "TARGET_USER_NOT_FOUND"


@pytest.mark.asyncio
async def test_home_permission_denied_error(
    client,
    auth_headers,
    mock_db,
):
    other_owner = await _create_user(mock_db, "owner2", "owner2@example.com")
    target_user = await _create_user(mock_db, "guest", "guest@example.com")

    home = Home(name="Foreign Home")
    async with mock_db.sessionmaker() as session:
        session.add(home)
        await session.flush()
        session.add(
            HomeUser(user_id=other_owner.id, home_id=home.id, user_type=UserType.OWNER)
        )
        await session.commit()

    res = await client.post(
        f"/homeuser/{home.id}/users",
        json={"user_email": target_user.email, "user_type": "guest"},
        headers=auth_headers,
    )

    assert res.status_code == 403
    body = res.json()
    assert body["error"] == "HOME_PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_owner_sees_only_own_homes(client, auth_headers):
    await client.post("/homes/", json={"name": "Home 1"}, headers=auth_headers)
    await client.post("/homes/", json={"name": "Home 2"}, headers=auth_headers)

    res = await client.get("/homes/", headers=auth_headers)

    assert res.status_code == 200
    homes = res.json()
    assert len(homes) == 2
