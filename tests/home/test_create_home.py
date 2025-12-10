import pytest


@pytest.mark.asyncio
async def test_create_home_success(client, auth_headers, mock_db):
    res = await client.post(
        "/homes/",
        json={"name": "My Home"},
        headers=auth_headers,
    )

    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "My Home"


@pytest.mark.asyncio
async def test_create_home_duplicate_name(client, auth_headers, mock_db):
    payload = {"name": "My Home"}

    first = await client.post("/homes/", json=payload, headers=auth_headers)
    assert first.status_code == 200

    response = await client.post("/homes/", json=payload, headers=auth_headers)

    assert response.status_code == 409
