import pytest


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
async def test_owner_sees_only_own_homes(client, auth_headers):
    await client.post("/homes/", json={"name": "Home 1"}, headers=auth_headers)
    await client.post("/homes/", json={"name": "Home 2"}, headers=auth_headers)

    res = await client.get("/homes/", headers=auth_headers)

    assert res.status_code == 200
    homes = res.json()
    assert len(homes) == 2
