from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from bot.models.domain import Budget, Expense
from decimal import Decimal
from datetime import datetime


class BudgetService:

    @staticmethod
    async def set_budget(
        session: AsyncSession,
        group_id: int,
        category: str,
        monthly_limit: Decimal,
        month: int = None,
        year: int = None,
    ) -> Budget:
        now = datetime.now()
        month = month or now.month
        year = year or now.year

        stmt = select(Budget).where(
            Budget.group_id == group_id,
            Budget.category == category,
            Budget.month == month,
            Budget.year == year,
        )
        result = await session.execute(stmt)
        budget = result.scalar_one_or_none()

        if budget:
            budget.monthly_limit = monthly_limit
        else:
            budget = Budget(
                group_id=group_id,
                category=category,
                month=month,
                year=year,
                monthly_limit=monthly_limit,
            )
            session.add(budget)

        await session.commit()
        await session.refresh(budget)
        return budget

    @staticmethod
    async def get_budgets(
        session: AsyncSession,
        group_id: int,
        month: int = None,
        year: int = None,
    ) -> list[dict]:
        """Retorna presupuestos con consumo real del mes."""
        now = datetime.now()
        month = month or now.month
        year = year or now.year

        budgets_stmt = select(Budget).where(
            Budget.group_id == group_id,
            Budget.month == month,
            Budget.year == year,
        )
        result = await session.execute(budgets_stmt)
        budgets = result.scalars().all()

        # Gasto real por categoría en ese mes
        from sqlalchemy import extract
        spent_stmt = (
            select(Expense.category, func.sum(Expense.amount).label("total"))
            .where(
                Expense.group_id == group_id,
                extract("month", Expense.expense_date) == month,
                extract("year", Expense.expense_date) == year,
            )
            .group_by(Expense.category)
        )
        spent_res = await session.execute(spent_stmt)
        spent_map = {row.category: Decimal(str(row.total)) for row in spent_res.all()}

        output = []
        for b in budgets:
            spent = spent_map.get(b.category, Decimal("0"))
            pct = (spent / b.monthly_limit * 100) if b.monthly_limit > 0 else Decimal("0")
            output.append(
                {
                    "category": b.category,
                    "limit": b.monthly_limit,
                    "spent": spent,
                    "remaining": b.monthly_limit - spent,
                    "pct": pct,
                    "over_budget": spent > b.monthly_limit,
                }
            )
        return output
