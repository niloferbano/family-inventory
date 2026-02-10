import pytest


@pytest.mark.asyncio
async def test_non_admin_cannot_list_users(client, auth_headers):
    res = await client.get("/users/", headers=auth_headers)

    assert res.status_code == 403
    body = res.json()
    assert body["detail"] == "Permission denied"


@pytest.mark.asyncio
async def test_admin_can_list_users(client, admin_headers):
    res = await client.get("/users/", headers=admin_headers)

    assert res.status_code == 200
    body = res.json()
    assert "results" in body
    assert body["count"] >= 1
