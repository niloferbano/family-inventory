from typing import Protocol, TypeVar, runtime_checkable


@runtime_checkable
class OrmModelProtocol(Protocol):
    id: int


OrmModelProtocolT = TypeVar(
    "OrmModelProtocolT",
    bound=OrmModelProtocol,
)
