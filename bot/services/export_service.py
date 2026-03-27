from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.models.domain import Expense, ShoppingItem, InventoryItem, Service
import pandas as pd
import tempfile
import os


class ExporterService:

    @staticmethod
    async def export_expenses_csv(
        session: AsyncSession, group_id: int, month: int = None, year: int = None
    ) -> str | None:
        from sqlalchemy import extract
        stmt = select(Expense).where(Expense.group_id == group_id)
        if month:
            stmt = stmt.where(extract("month", Expense.expense_date) == month)
        if year:
            stmt = stmt.where(extract("year", Expense.expense_date) == year)
        stmt = stmt.order_by(Expense.expense_date.desc())

        result = await session.execute(stmt)
        expenses = result.scalars().all()
        if not expenses:
            return None

        data = [
            {
                "ID": e.id,
                "Fecha": e.expense_date.strftime("%Y-%m-%d"),
                "Monto": float(e.amount),
                "Categoría": e.category,
                "Compartido": "Sí" if e.shared else "No",
                "Saldado": "Sí" if e.is_settled else "No",
                "Nota": e.description or "",
            }
            for e in expenses
        ]
        return ExporterService._write_csv(data, prefix="gastos")

    @staticmethod
    async def export_shopping_csv(session: AsyncSession, group_id: int) -> str | None:
        stmt = (
            select(ShoppingItem)
            .where(ShoppingItem.group_id == group_id)
            .order_by(ShoppingItem.status.asc(), ShoppingItem.item_name.asc())
        )
        result = await session.execute(stmt)
        items = result.scalars().all()
        if not items:
            return None

        data = [
            {
                "Producto": i.item_name,
                "Cantidad": float(i.quantity) if i.quantity else "",
                "Unidad": i.unit or "",
                "Prioridad": i.priority,
                "Estado": i.status,
                "Categoría": i.category or "",
            }
            for i in items
        ]
        return ExporterService._write_csv(data, prefix="lista_compras")

    @staticmethod
    async def export_inventory_csv(session: AsyncSession, group_id: int) -> str | None:
        stmt = (
            select(InventoryItem)
            .where(InventoryItem.group_id == group_id)
            .order_by(InventoryItem.item_name.asc())
        )
        result = await session.execute(stmt)
        items = result.scalars().all()
        if not items:
            return None

        data = [
            {
                "Producto": i.item_name,
                "Cantidad actual": float(i.current_quantity),
                "Mínimo": float(i.minimum_quantity),
                "Unidad": i.unit or "",
                "Estado": "⚠️ Bajo" if i.current_quantity <= i.minimum_quantity else "✅ OK",
            }
            for i in items
        ]
        return ExporterService._write_csv(data, prefix="inventario")

    @staticmethod
    def _write_csv(data: list[dict], prefix: str) -> str:
        df = pd.DataFrame(data)
        fd, path = tempfile.mkstemp(suffix=".csv", prefix=f"{prefix}_")
        with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
            df.to_csv(f, index=False)
        return path

    @staticmethod
    def cleanup(path: str):
        """Eliminar archivo temporal después de enviarlo."""
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
