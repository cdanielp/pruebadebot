from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from bot.models.domain import Expense, AuditLog, Budget
from decimal import Decimal
from datetime import datetime, date
import json


class ExpenseService:

    @staticmethod
    async def create_expense(
        session: AsyncSession,
        group_id: int,
        creator_id: int,
        payer_id: int,
        amount: Decimal,
        category: str,
        description: str = "",
        shared: bool = True,
        split_type: str = "50_50",
    ) -> Expense:
        expense = Expense(
            group_id=group_id,
            created_by_user_id=creator_id,
            paid_by_user_id=payer_id,
            amount=amount,
            category=category,
            description=description,
            shared=shared,
            split_type=split_type,
        )
        session.add(expense)
        await session.flush()

        audit = AuditLog(
            group_id=group_id,
            actor_user_id=creator_id,
            entity_type="Expense",
            entity_id=expense.id,
            action="CREATE",
            before_json=None,
            after_json={
                "amount": str(amount),
                "category": category,
                "paid_by": payer_id,
                "shared": shared,
                "split_type": split_type,
            },
        )
        session.add(audit)
        await session.commit()
        await session.refresh(expense)
        return expense

    @staticmethod
    async def update_expense(
        session: AsyncSession,
        expense_id: int,
        actor_id: int,
        group_id: int,
        **fields,
    ) -> Expense:
        expense = await session.get(Expense, expense_id)
        if not expense or expense.group_id != group_id:
            raise ValueError("Gasto no encontrado o sin permisos.")

        old_data = {
            "amount": str(expense.amount),
            "category": expense.category,
            "description": expense.description,
            "shared": expense.shared,
        }

        for key, value in fields.items():
            if hasattr(expense, key):
                setattr(expense, key, value)

        session.add(expense)
        await session.flush()

        audit = AuditLog(
            group_id=group_id,
            actor_user_id=actor_id,
            entity_type="Expense",
            entity_id=expense.id,
            action="UPDATE",
            before_json=old_data,
            after_json={k: str(v) if isinstance(v, Decimal) else v for k, v in fields.items()},
        )
        session.add(audit)
        await session.commit()
        await session.refresh(expense)
        return expense

    @staticmethod
    async def delete_expense(
        session: AsyncSession, expense_id: int, actor_id: int, group_id: int
    ):
        expense = await session.get(Expense, expense_id)
        if not expense or expense.group_id != group_id:
            raise ValueError("Gasto no encontrado o sin permisos.")

        old_data = {
            "amount": str(expense.amount),
            "category": expense.category,
            "paid_by": expense.paid_by_user_id,
            "description": expense.description,
        }

        await session.delete(expense)

        audit = AuditLog(
            group_id=group_id,
            actor_user_id=actor_id,
            entity_type="Expense",
            entity_id=expense_id,
            action="DELETE",
            before_json=old_data,
            after_json=None,
        )
        session.add(audit)
        await session.commit()

    @staticmethod
    async def get_expenses(
        session: AsyncSession,
        group_id: int,
        date_from: datetime = None,
        date_to: datetime = None,
        category: str = None,
        payer_id: int = None,
        limit: int = 50,
    ) -> list[Expense]:
        stmt = select(Expense).where(Expense.group_id == group_id)
        if date_from:
            stmt = stmt.where(Expense.expense_date >= date_from)
        if date_to:
            stmt = stmt.where(Expense.expense_date <= date_to)
        if category:
            stmt = stmt.where(Expense.category == category)
        if payer_id:
            stmt = stmt.where(Expense.paid_by_user_id == payer_id)
        stmt = stmt.order_by(Expense.expense_date.desc()).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_expense_by_id(
        session: AsyncSession, expense_id: int, group_id: int
    ) -> Expense | None:
        expense = await session.get(Expense, expense_id)
        if expense and expense.group_id == group_id:
            return expense
        return None
