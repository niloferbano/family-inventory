import math
from enum import StrEnum, auto
from typing import (Annotated, Any, Generic, Literal, Protocol, Type,
                    TypeAlias, TypeVar)
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import annotated_types
import sqlalchemy as sa
from fastapi import HTTPException, status
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.functions import func

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 10

AnyTuple = TypeVar("AnyTuple", bound=tuple)
IdAttribute = TypeVar("IdAttribute")
FieldT = InstrumentedAttribute[IdAttribute] | InstrumentedAttribute[IdAttribute | None]


GenericT = TypeVar("GenericT")
PaginatedType = TypeVar("PaginatedType", bound="PaginatedOutput")
OrmModelProtocolT = TypeVar("OrmModelProtocolT", bound="OrmModelProtocol")


class PaginationMode(StrEnum):
    LIMIT_SKIP = auto()
    PAGE = auto()


def get_limit_skip(page: int, page_size: int) -> tuple[int, int]:
    limit = page_size
    offset = (page - 1) * limit
    return limit, offset


PageSizeT: TypeAlias = Annotated[int, annotated_types.Interval(ge=1, le=100)]
PageT: TypeAlias = Annotated[int, annotated_types.Ge(1)]
SkipT: TypeAlias = Annotated[int, annotated_types.Ge(0)]


class Page(BaseModel):
    mode: Literal[PaginationMode.PAGE] = PaginationMode.PAGE
    page_size: PageSizeT
    page: PageT

    def to_limit(self) -> tuple[int, int]:
        limit, skip = get_limit_skip(self.page, self.page_size)
        return Limit(limit=limit, skip=skip).to_limit()


class Limit(BaseModel):
    mode: Literal[PaginationMode.LIMIT_SKIP] = PaginationMode.LIMIT_SKIP
    limit: PageSizeT
    skip: SkipT

    def to_limit(self) -> tuple[int, int]:
        return self.limit, self.skip


class PaginationParams(BaseModel):
    page: PageT = DEFAULT_PAGE
    page_size: PageSizeT = DEFAULT_PER_PAGE


PaginationT = Annotated[Page | Limit, Field(discriminator="mode")]


async def apply_pagination_without_class(
    query: sa.Select[AnyTuple],
    session: AsyncSession,
    sort_by: FieldT,
    pagination: PaginationT,
    extra_col_label: str = "__total_count",
    sort_mode: Literal["asc", "desc"] = "desc",
) -> tuple[list[AnyTuple], int]:
    """
    Apply pagination to the query, execute it and return the list of rows returned by the query.
    Also get the total count of that query which is useful to show to the client.

    Automatically removes the extra column it adds to the query result.
    """
    limit, skip = pagination.to_limit()
    query = query.order_by(sort_by.desc() if sort_mode == "desc" else sort_by.asc())
    query = query.add_columns(sa.func.count().over().label(extra_col_label))

    if limit is not None:
        query = query.limit(limit)
    if skip is not None:
        query = query.offset(skip)

    result = (await session.execute(query)).all()
    total_size = result[0].tuple()[-1] if result else 0
    result = [tuple(row.tuple()[:-1]) for row in result]
    return result, total_size  # type: ignore


class OrmModelProtocol(Protocol):
    @classmethod
    def from_orm(cls, instance: Any) -> Any: ...


class PaginatedOutput(BaseModel, Generic[GenericT]):
    count: int
    total_pages: int
    next: str | None
    previous: str | None
    results: list[GenericT]


def update_pagination(url: str, page: int, page_size: int) -> str:
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    query_params["page"] = [str(page)]
    query_params["page_size"] = [str(page_size)]

    updated_query = urlencode(query_params, doseq=True)

    updated_url = urlunparse(parsed_url._replace(query=updated_query))

    return updated_url


async def apply_pagination(
    query: sa.Select[AnyTuple],
    session: AsyncSession,
    sort_by: FieldT,
    pagination: Page,
    base_url: str,
    row_model: Type[OrmModelProtocolT],
    paginated_output_model: Type[PaginatedType] = PaginatedOutput,
    extra_col_label: str = "__total_count",
    sort_mode: Literal["asc", "desc"] = "desc",
) -> PaginatedType:
    """
    Apply pagination to the query, execute it and return the list of rows returned by the query.
    Also get the total count of that query which is useful to show to the client.

    Automatically removes the extra column it adds to the query result.


    Usage:
    from fastapi import Request
    from smartlane_utils.sqla import get_pagination

    @router.get(
    "/",
    response_model=PaginatedOutput,
    )
    async def get_or_create_postal_codes(
        request: Request,
        page: int = DEFAULT_PAGE,
        page_size: int = DEFAULT_PER_PAGE,
    ) -> PaginatedOutput: ...

    class GetModel(BaseModel):
          name: str

          @classmethod
          def from_orm(cls, instance: OrmModel) -> BaseModel:
            return GetModel(**instance)

    pagination = get_pagination(page_size=page_size, page=page)
    results = await apply_pagination(
        query=query, session=session, sort_by=PostalCode.id, pagination=pagination, base_url=str(request.url),
          pydantic_model=GetModel
    )
    """
    original_query = query
    limit, skip = pagination.to_limit()
    query = query.order_by(sort_by.desc() if sort_mode == "desc" else sort_by.asc())
    query = query.add_columns(sa.func.count().over().label(extra_col_label))

    if limit is not None:
        query = query.limit(limit)
    if skip is not None:
        query = query.offset(skip)

    result = (await session.execute(query)).all()
    if result != []:
        total_size = result[0].tuple()[-1] if result else 0
        total_pages = math.ceil(total_size / pagination.page_size)

        next_url = (
            update_pagination(base_url, pagination.page + 1, pagination.page_size)
            if pagination.page < total_pages
            else None
        )
        prev_url = (
            update_pagination(base_url, pagination.page - 1, pagination.page_size)
            if pagination.page > 1
            else None
        )
    else:
        count_query = sa.select(func.count()).select_from(original_query.subquery())

        total_size = (await session.execute(count_query)).scalar() or 0
        total_pages = math.ceil(total_size / pagination.page_size)
        next_url = (
            update_pagination(base_url, pagination.page + 1, pagination.page_size)
            if pagination.page < total_pages
            else None
        )
        if total_size == 0:
            prev_url = None
        elif pagination.page > total_pages:
            prev_url = update_pagination(base_url, total_pages, pagination.page_size)
        elif pagination.page > 1:
            prev_url = update_pagination(
                base_url, pagination.page - 1, pagination.page_size
            )
        else:
            prev_url = None

    result = [
        row_model.from_orm(row[0] if len(row) == 1 else row) for *row, _ in result
    ]

    return paginated_output_model(
        total=total_size,
        next=next_url,
        previous=prev_url,
        results=result,
        total_pages=total_pages,
    )


def get_pagination(
    page_size: PageSizeT | None = DEFAULT_PER_PAGE,
    page: PageT | None = DEFAULT_PAGE,
    limit: PageSizeT | None = None,
    skip: SkipT | None = None,
) -> Page:
    acceptable_condition_1 = (limit, skip) == (None, None) and None not in (
        page_size,
        page,
    )
    acceptable_condition_2 = page is None and None not in (limit, skip)

    if not (acceptable_condition_1 or acceptable_condition_2):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must provide either (limit,skip) or (page,page_size) pair",
        )

    try:
        result = TypeAdapter(Page).validate_python(
            {
                "page_size": page_size,
                "page": page,
                "limit": limit,
                "skip": skip,
            }
        )
    except ValidationError as ex:
        errors = [
            {
                "loc": err["loc"],
                "msg": err["msg"],
                "type": err["type"],
            }
            for err in ex.errors()
        ]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=errors,
        )

    return result
