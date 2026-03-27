from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.models.domain import Service, ServicePayment
from decimal import Decimal
from datetime import datetime


class ServiceManager:

    @staticmethod
    async def create_service(
        session: AsyncSession,
        group_id: int,
        name: str,
        due_day: int,
        estimated_amount: Decimal = None,
        paid_by_user_id: int = None,
        shared: bool = True,
    ) -> Service:
        svc = Service(
            group_id=group_id,
            name=name.strip().lower(),
            due_day=due_day,
            estimated_amount=estimated_amount,
            paid_by_user_id=paid_by_user_id,
            shared=shared,
        )
        session.add(svc)
        await session.commit()
        await session.refresh(svc)
        return svc

    @staticmethod
    async def get_services(
        session: AsyncSession, group_id: int, only_active: bool = True
    ) -> list[Service]:
        stmt = select(Service).where(Service.group_id == group_id)
        if only_active:
            stmt = stmt.where(Service.is_active == True)
        stmt = stmt.order_by(Service.due_day.asc())
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def mark_paid(
        session: AsyncSession,
        group_id: int,
        service_name: str,
        amount_paid: Decimal,
        paid_by_user_id: int,
        note: str = "",
    ) -> tuple[Service, ServicePayment] | tuple[None, None]:
        stmt = select(Service).where(
            Service.group_id == group_id,
            Service.name == service_name.strip().lower(),
            Service.is_active == True,
        )
        result = await session.execute(stmt)
        svc = result.scalar_one_or_none()
        if not svc:
            return None, None

        svc.last_paid_date = datetime.now()
        session.add(svc)

        payment = ServicePayment(
            service_id=svc.id,
            group_id=group_id,
            amount_paid=amount_paid,
            paid_by_user_id=paid_by_user_id,
            note=note,
        )
        session.add(payment)
        await session.commit()
        await session.refresh(svc)
        await session.refresh(payment)
        return svc, payment

    @staticmethod
    async def get_upcoming(
        session: AsyncSession, group_id: int, within_days: int = 7
    ) -> list[Service]:
        """Servicios cuyo día de pago cae dentro de los próximos N días del mes."""
        from datetime import date
        today = date.today()
        upcoming_days = [(today.day + i - 1) % 31 + 1 for i in range(within_days + 1)]

        stmt = select(Service).where(
            Service.group_id == group_id,
            Service.is_active == True,
            Service.due_day.in_(upcoming_days),
        ).order_by(Service.due_day.asc())
        result = await session.execute(stmt)
        return result.scalars().all()
