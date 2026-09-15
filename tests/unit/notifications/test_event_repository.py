from uuid import uuid4

import pytest

from app.apis.notifications.models import NotificationEvent
from app.apis.notifications.repository import NotificationEventRepository


@pytest.mark.asyncio
async def test_create_and_get_event(mock_db):
    async with mock_db.begin() as session:
        event = await NotificationEventRepository(session).create(
            NotificationEvent(
                source="users",
                event_type="test.event",
                message="original",
                recipients={},
            )
        )
        event_id = event.id
    async with mock_db.begin() as session:
        repo = NotificationEventRepository(session)
        event = await repo.get(event_id)
        assert event.message == "original"
        assert event.source == "users"
        assert await repo.get(uuid4()) is None


@pytest.mark.asyncio
async def test_duplicate_event_preserves_original_content(mock_db):
    event_id = uuid4()
    for message in ("original", "redelivered"):
        async with mock_db.begin() as session:
            await NotificationEventRepository(session).create_if_missing(
                event_id=event_id,
                source="users",
                event_type="test.event",
                subject=message,
                message=message,
                recipients={"snapshot": message},
            )
    async with mock_db.begin() as session:
        event = await NotificationEventRepository(session).get(event_id)
        assert event.message == "original"
        assert event.subject == "original"
        assert event.recipients == {"snapshot": "original"}


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["create", "create_if_missing"])
async def test_event_creation_rolls_back_with_caller(mock_db, method):
    event_id = uuid4()
    with pytest.raises(RuntimeError):
        async with mock_db.begin() as session:
            repo = NotificationEventRepository(session)
            values = dict(
                source="users",
                event_type="test.event",
                subject=None,
                message="test",
                recipients={},
            )
            if method == "create":
                await repo.create(NotificationEvent(id=event_id, **values))
            else:
                await repo.create_if_missing(event_id=event_id, **values)
            raise RuntimeError("Roll back")
    async with mock_db.begin() as session:
        assert await NotificationEventRepository(session).get(event_id) is None
