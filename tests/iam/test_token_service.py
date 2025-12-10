# tests/iam/test_activation_key.py
import pytest
from pydantic import BaseModel

from app.iam.types import ActivationKey


class ActivationModel(BaseModel):
    key: ActivationKey


def test_valid_activation_key():
    value = "IevKSEhjoUQCb6iT0wmMSpiI1NprDZuEUtVDN7OC1N0"
    key = ActivationKey(value)
    assert isinstance(key, ActivationKey)
    assert str(key) == value


def test_invalid_token_format():
    invalid = "!!!!not-valid!!!!"
    with pytest.raises(ValueError):
        ActivationKey(invalid)


def test_token_too_short():
    short = "abc123"
    with pytest.raises(ValueError):
        ActivationKey(short)


def test_token_too_long():
    long = "a" * 101  # > 100 chars
    with pytest.raises(ValueError):
        ActivationKey(long)


def test_non_string_input():
    with pytest.raises(TypeError):
        ActivationKey(1234)  # type: ignore


def test_repr_hides_value():
    key = ActivationKey("A" * 30)
    assert repr(key) == "ActivationKey(<hidden>)"
