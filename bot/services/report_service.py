from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, extract
from bot.models.domain import Expense, Task, Service, ShoppingItem, GroupMember, User
from bot.services.balance_service import BalanceService
from decimal import Decimal
from datetime import datetime, timedelta


class ReportService:

    @staticmethod
    async def weekly_summary(session: AsyncSession, group_id: int) -> dict:
        now = datetime.now()
        week_ago = now - timedelta(days=7)

        # Gastos de la semana
        expenses_stmt = select(Expense).where(
            Expense.group_id == group_id,
            Expense.expense_date >= week_ago,
        )
        expenses_res = await session.execute(expenses_stmt)
        expenses = expenses_res.scalars().all()

        total = sum(Decimal(str(e.amount)) for e in expenses)

        # Top 3 categorías
        cat_stmt = (
            select(Expense.category, func.sum(Expense.amount).label("total"))
            .where(Expense.group_id == group_id, Expense.expense_date >= week_ago)
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
            .limit(3)
        )
        cat_res = await session.execute(cat_stmt)
        top_cats = [(row.category, Decimal(str(row.total))) for row in cat_res.all()]

        # Pagado por cada quien
        payer_stmt = (
            select(Expense.paid_by_user_id, func.sum(Expense.amount).label("total"))
            .where(Expense.group_id == group_id, Expense.expense_date >= week_ago)
            .group_by(Expense.paid_by_user_id)
        )
        payer_res = await session.execute(payer_stmt)
        by_payer = {row.paid_by_user_id: Decimal(str(row.total)) for row in payer_res.all()}

        # Balance actual
        balance = await BalanceService.calculate_balance(session, group_id)

        # Tareas pendientes
        task_stmt = select(Task).where(
            Task.group_id == group_id,
            Task.status.in_(("pendiente", "en_progreso")),
        )
        task_res = await session.execute(task_stmt)
        pending_tasks = task_res.scalars().all()

        # Urgentes en lista de compras
        urgent_stmt = select(ShoppingItem).where(
            ShoppingItem.group_id == group_id,
            ShoppingItem.status == "urgente",
        )
        urgent_res = await session.execute(urgent_stmt)
        urgent_items = urgent_res.scalars().all()

        # Servicios próximos (7 días)
        from bot.services.service_manager import ServiceManager
        upcoming_services = await ServiceManager.get_upcoming(session, group_id, within_days=7)

        return {
            "period": "semana",
            "total_spent": total,
            "top_categories": top_cats,
            "by_payer": by_payer,
            "balance": balance,
            "pending_tasks": pending_tasks,
            "urgent_items": urgent_items,
            "upcoming_services": upcoming_services,
        }

    @staticmethod
    async def monthly_summary(session: AsyncSession, group_id: int) -> dict:
        now = datetime.now()
        month = now.month
        year = now.year

        # Gastos del mes
        cat_stmt = (
            select(Expense.category, func.sum(Expense.amount).label("total"))
            .where(
                Expense.group_id == group_id,
                extract("month", Expense.expense_date) == month,
                extract("year", Expense.expense_date) == year,
            )
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
        )
        cat_res = await session.execute(cat_stmt)
        by_category = [(row.category, Decimal(str(row.total))) for row in cat_res.all()]
        total = sum(v for _, v in by_category)

        balance = await BalanceService.calculate_balance(session, group_id)

        return {
            "period": "mes",
            "month": month,
            "year": year,
            "total_spent": total,
            "by_category": by_category,
            "balance": balance,
        }
