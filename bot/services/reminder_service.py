from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.models.domain import Reminder
from datetime import datetime


class ReminderService:

    @staticmethod
    async def create_reminder(
        session: AsyncSession,
        group_id: int,
        chat_id: int,
        creator_id: int,
        title: str,
        scheduled_at: datetime,
        schedule_type: str = "once",
        recurrence_rule: str = None,
        user_id: int = None,
    ) -> Reminder:
        reminder = Reminder(
            group_id=group_id,
            chat_id=chat_id,
            user_id=user_id,
            created_by_user_id=creator_id,
            title=title.strip(),
            scheduled_at=scheduled_at,
            schedule_type=schedule_type,
            recurrence_rule=recurrence_rule,
            status="activo",
        )
        session.add(reminder)
        await session.commit()
        await session.refresh(reminder)
        return reminder

    @staticmethod
    async def get_active(
        session: AsyncSession, group_id: int
    ) -> list[Reminder]:
        stmt = (
            select(Reminder)
            .where(
                Reminder.group_id == group_id,
                Reminder.status == "activo",
            )
            .order_by(Reminder.scheduled_at.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def cancel_reminder(
        session: AsyncSession, reminder_id: int, group_id: int
    ) -> bool:
        reminder = await session.get(Reminder, reminder_id)
        if reminder and reminder.group_id == group_id:
            reminder.status = "cancelado"
            session.add(reminder)
            await session.commit()
            return True
        return False

    @staticmethod
    async def mark_done(session: AsyncSession, reminder_id: int):
        reminder = await session.get(Reminder, reminder_id)
        if reminder:
            reminder.status = "completado"
            session.add(reminder)
            await session.commit()

    @staticmethod
    async def get_all_active_for_scheduling(session: AsyncSession) -> list[Reminder]:
        """Para rehidratar el scheduler al arrancar."""
        now = datetime.now()
        stmt = select(Reminder).where(
            Reminder.status == "activo",
            Reminder.scheduled_at >= now,
        )
        result = await session.execute(stmt)
        return result.scalars().all()
