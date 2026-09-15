from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.notifications.models import NotificationOutbox


class NotificationOutboxRepository:
    """Manage outbox rows within the caller's transaction; never commit here."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def add(self, notification: NotificationOutbox) -> NotificationOutbox:
        """Stage an existing outbox object without flushing the transaction."""
        self.session.add(notification)
        return notification

    async def create(
        self,
        *,
        event_id: UUID,
        topic: str,
        payload: dict,
        headers: dict | None = None,
    ) -> NotificationOutbox:
        """Construct and flush an outbox row without committing it."""
        notification = self.add(
            NotificationOutbox(
                event_id=event_id,
                topic=topic,
                payload=payload,
                headers=headers if headers is not None else {},
            )
        )
        await self.session.flush()
        return notification

    async def delete(self, notification: NotificationOutbox) -> None:
        """Mark a persisted outbox row for deletion in the caller's transaction."""
        await self.session.delete(notification)

    async def claim_for_send(
        self, *, now: datetime, limit: int, max_attempts: int
    ) -> list[NotificationOutbox]:
        claimable = (
            sa.select(NotificationOutbox.id)
            .where(NotificationOutbox.attempt_count < max_attempts)
            .where(NotificationOutbox.status.in_(["PENDING", "FAILED"]))
            .where(
                sa.or_(
                    NotificationOutbox.next_retry_at.is_(None),
                    NotificationOutbox.next_retry_at <= now,
                )
            )
            .order_by(NotificationOutbox.created_at.asc(), NotificationOutbox.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
            .subquery()
        )

        # Mark as SENDING + bump attempt_count while holding the row locks
        stmt = (
            sa.update(NotificationOutbox)
            .where(NotificationOutbox.id.in_(sa.select(claimable.c.id)))
            .values(
                status="SENDING",
                attempt_count=NotificationOutbox.attempt_count + 1,
                updated_at=now,
            )
            .returning(NotificationOutbox)
        )

        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def finalize_results(
        self, results: dict[UUID, dict[str, Any]], *, now: datetime
    ) -> None:
        if not results:
            return
        ids = list(results.keys())

        status_case = sa.case(
            {rid: results[rid]["status"] for rid in ids},
            value=NotificationOutbox.id,
            else_=NotificationOutbox.status,
        )
        last_error_case = sa.case(
            {rid: results[rid]["last_error"] for rid in ids},
            value=NotificationOutbox.id,
            else_=NotificationOutbox.last_error,
        )
        next_retry_case = sa.case(
            {rid: results[rid]["next_retry_at"] for rid in ids},
            value=NotificationOutbox.id,
            else_=NotificationOutbox.next_retry_at,
        )

        await self.session.execute(
            sa.update(NotificationOutbox)
            .where(NotificationOutbox.id.in_(ids))
            .values(
                status=status_case,
                last_error=last_error_case,
                next_retry_at=next_retry_case,
                updated_at=now,
            )
        )

    async def ensure(self, values: dict) -> tuple:
        tbl = NotificationOutbox.__table__
        event_id = values["event_id"]
        insert_stmt = (
            pg_insert(NotificationOutbox)
            .values(values)
            .on_conflict_do_nothing(index_elements=[tbl.c.event_id])
            .returning(tbl.c.id, tbl.c.status, tbl.c.attempt_count)
        )

        inserted = (await self.session.execute(insert_stmt)).one_or_none()
        if inserted is not None:
            outbox_id, status, attempt_count = inserted
        else:
            existing = (
                await self.session.execute(
                    sa.select(tbl.c.id, tbl.c.status, tbl.c.attempt_count)
                    .where(tbl.c.event_id == event_id)
                    .limit(1)
                )
            ).one_or_none()
            if existing is None:
                # Extremely unlikely (race + rollback). Treat as a retryable error.
                raise RuntimeError(
                    f"Outbox row missing after insert/select for event_id={event_id}"
                )
            outbox_id, status, attempt_count = existing

        return outbox_id, status, attempt_count

    async def claim_one(
        self, outbox_id: UUID, *, now: datetime, max_attempts: int
    ) -> int | None:
        claim_stmt = (
            sa.update(NotificationOutbox)
            .where(NotificationOutbox.id == outbox_id)
            .where(sa.func.upper(NotificationOutbox.status).in_(["PENDING", "FAILED"]))
            .where(
                sa.or_(
                    NotificationOutbox.next_retry_at.is_(None),
                    NotificationOutbox.next_retry_at <= now,
                )
            )
            .where(NotificationOutbox.attempt_count < max_attempts)
            .values(
                status="SENDING",
                attempt_count=NotificationOutbox.attempt_count + 1,
                updated_at=now,
            )
            .returning(NotificationOutbox.attempt_count)
        )

        return (await self.session.execute(claim_stmt)).scalar_one_or_none()

    async def get_state(self, outbox_id: UUID):
        return (
            await self.session.execute(
                sa.select(
                    NotificationOutbox.status,
                    NotificationOutbox.attempt_count,
                    NotificationOutbox.next_retry_at,
                ).where(NotificationOutbox.id == outbox_id)
            )
        ).one_or_none()

    async def update(
        self,
        outbox_id: UUID,
        *,
        status: str,
        last_error: str | None,
        next_retry_at: datetime | None,
        updated_at: datetime,
    ) -> None:
        await self.session.execute(
            sa.update(NotificationOutbox)
            .where(NotificationOutbox.id == outbox_id)
            .values(
                status=status,
                last_error=last_error,
                next_retry_at=next_retry_at,
                updated_at=updated_at,
            )
        )
