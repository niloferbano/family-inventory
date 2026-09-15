from uuid import uuid4

import pytest
from sqlalchemy import select

from app.apis.notifications.models import NotificationOutbox
from app.apis.notifications.repository import NotificationOutboxRepository


@pytest.mark.asyncio
async def test_create_and_delete_outbox(mock_db):
    async with mock_db.begin() as session:
        row = await NotificationOutboxRepository(session).create(
            event_id=uuid4(), topic="test.event", payload={"message": "test"}
        )
        row_id = row.id
    async with mock_db.begin() as session:
        row = await session.get(NotificationOutbox, row_id)
        assert row.status == "PENDING"
        assert row.headers == {}
        assert row.payload == {"message": "test"}
        await NotificationOutboxRepository(session).delete(row)
    async with mock_db.begin() as session:
        assert await session.get(NotificationOutbox, row_id) is None


@pytest.mark.asyncio
async def test_add_outbox_rolls_back_with_caller(mock_db):
    event_id = uuid4()
    with pytest.raises(RuntimeError):
        async with mock_db.begin() as session:
            NotificationOutboxRepository(session).add(
                NotificationOutbox(event_id=event_id, topic="test.event", payload={})
            )
            await session.flush()
            raise RuntimeError("Roll back the caller's transaction")
    async with mock_db.begin() as session:
        assert (
            await session.scalar(
                select(NotificationOutbox).where(
                    NotificationOutbox.event_id == event_id
                )
            )
            is None
        )
