from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.apis.product.models import Product
from app.apis.product.repository import ProductRepository
from app.core.database.session import get_db
from app.iam.dependencies import get_current_user
from app.schemas_base.base import BaseApiSchema

router = APIRouter(
    prefix="/products", tags=["Products"], dependencies=[Depends(get_current_user)]
)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ProductRead(BaseApiSchema):
    id: UUID
    name: str


@router.get("", response_model=list[ProductRead])
async def search_products(
    q: str = Query(min_length=1, max_length=100), db_manager=Depends(get_db)
):
    async with db_manager.begin() as session:
        return await ProductRepository(session).search_by_name(q)


@router.post("", response_model=ProductRead, status_code=201)
async def create_product(payload: ProductCreate, db_manager=Depends(get_db)):
    async with db_manager.begin() as session:
        return await ProductRepository(session).create(Product(name=payload.name))
