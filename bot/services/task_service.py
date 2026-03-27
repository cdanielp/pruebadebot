from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.models.domain import Task, AuditLog
from datetime import datetime


class TaskService:

    @staticmethod
    async def create_task(
        session: AsyncSession,
        group_id: int,
        creator_id: int,
        title: str,
        description: str = "",
        assigned_to: int = None,
        due_at: datetime = None,
        recurrence: str = None,
    ) -> Task:
        task = Task(
            group_id=group_id,
            title=title.strip(),
            description=description,
            assigned_to_user_id=assigned_to,
            due_at=due_at,
            recurrence_rule=recurrence,
            status="pendiente",
            created_by_user_id=creator_id,
        )
        session.add(task)
        await session.flush()

        audit = AuditLog(
            group_id=group_id,
            actor_user_id=creator_id,
            entity_type="Task",
            entity_id=task.id,
            action="CREATE",
            before_json=None,
            after_json={"title": title, "assigned_to": assigned_to},
        )
        session.add(audit)
        await session.commit()
        await session.refresh(task)
        return task

    @staticmethod
    async def get_pending(
        session: AsyncSession, group_id: int
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(
                Task.group_id == group_id,
                Task.status.in_(("pendiente", "en_progreso")),
            )
            .order_by(Task.due_at.asc().nullslast(), Task.created_at.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_overdue(session: AsyncSession, group_id: int) -> list[Task]:
        now = datetime.now()
        stmt = (
            select(Task)
            .where(
                Task.group_id == group_id,
                Task.status.in_(("pendiente", "en_progreso")),
                Task.due_at < now,
            )
            .order_by(Task.due_at.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def mark_done(
        session: AsyncSession,
        task_id: int,
        group_id: int,
        actor_id: int,
    ) -> Task | None:
        task = await session.get(Task, task_id)
        if not task or task.group_id != group_id:
            return None

        task.status = "completada"
        session.add(task)

        audit = AuditLog(
            group_id=group_id,
            actor_user_id=actor_id,
            entity_type="Task",
            entity_id=task_id,
            action="UPDATE",
            before_json={"status": "pendiente"},
            after_json={"status": "completada"},
        )
        session.add(audit)
        await session.commit()
        await session.refresh(task)
        return task

    @staticmethod
    async def find_by_title(
        session: AsyncSession, group_id: int, title: str
    ) -> Task | None:
        stmt = select(Task).where(
            Task.group_id == group_id,
            Task.title.ilike(f"%{title.strip()}%"),
            Task.status.in_(("pendiente", "en_progreso")),
        )
        result = await session.execute(stmt)
        return result.scalars().first()
