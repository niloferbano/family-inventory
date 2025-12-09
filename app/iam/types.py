import re

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema


class HashedString(str):
    """A string type representing hashed passwords."""

    def __repr__(self) -> str:
        return "HashedString(<hidden>)"

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        # Accept any string and convert to HashedString
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if not isinstance(value, str):
            raise TypeError("HashedString must be created from a string")
        return cls(value)


TOKEN_REGEX = re.compile(r"^[A-Za-z0-9_\-]{20,100}$")


class ActivationKey(str):
    """
    Custom strong type for activation tokens stored in Redis.
    Ensures validation + secure repr.
    """

    def __new__(cls, value: str):
        if not isinstance(value, str):
            raise TypeError("ActivationKey must be a string.")

        if not TOKEN_REGEX.match(value):
            raise ValueError("Invalid activation token format.")

        return super().__new__(cls, value)

    def __repr__(self) -> str:
        return "ActivationKey(<hidden>)"

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, str):
            raise TypeError("ActivationKey must be a string")
        if not TOKEN_REGEX.match(v):
            raise ValueError("Invalid activation token format")
        return cls(v)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
        )
