import pytest

from app.apis.homes.models import Home
from app.apis.notifications.models import NotificationSubscription
from app.apis.notifications.repository import NotificationSubscriptionRepository
from app.apis.notifications.types import NotificationChannel
from app.apis.users.models import User


@pytest.mark.asyncio
async def test_topic_matching_filters_disabled_other_home_and_other_user(mock_db):
    async with mock_db.begin() as session:
        homes = [Home(name="one"), Home(name="two")]
        users = [
            User(username=name, email=f"{name}@example.com", hashed_password="unused")
            for name in ("one", "two")
        ]
        session.add_all(homes + users)
        await session.flush()
        repo = NotificationSubscriptionRepository(session)
        rows = []
        for home, user, topic, enabled in [
            (0, 0, "inventory.item.expired", True),
            (0, 0, "inventory.item.*", True),
            (0, 0, "inventory.item.expiring", False),
            (0, 0, "users.*", True),
            (1, 0, "inventory.item.*", True),
            (0, 1, "inventory.item.*", True),
        ]:
            rows.append(
                await repo.create(
                    NotificationSubscription(
                        home_id=homes[home].id,
                        user_id=users[user].id,
                        topic=topic,
                        enabled=enabled,
                        channel=NotificationChannel.EMAIL,
                    )
                )
            )
        matches = await repo.list_enabled_for_topic(
            home_id=homes[0].id, topic="inventory.item.expired", user_id=users[0].id
        )
        assert {row.id for row in matches} == {rows[0].id, rows[1].id}
        matches = await repo.list_enabled_for_topic(
            home_id=homes[0].id, topic="inventory.item.expiring"
        )
        assert {row.id for row in matches} == {rows[1].id, rows[5].id}
