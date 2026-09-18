import pytest


@pytest.mark.asyncio
async def test_create_and_search_product(client, auth_headers):
    response = await client.post(
        "/products", json={"name": "Milk"}, headers=auth_headers
    )
    assert response.status_code == 201
    product = response.json()
    assert product["id"]
    assert product["name"] == "Milk"
    response = await client.get("/products?q=Milk", headers=auth_headers)
    assert response.status_code == 200
    assert product in response.json()


@pytest.mark.asyncio
async def test_products_require_authentication(client):
    assert (await client.get("/products?q=Milk")).status_code == 401
    assert (await client.post("/products", json={"name": "Milk"})).status_code == 401
