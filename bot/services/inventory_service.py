from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.models.domain import InventoryItem
from decimal import Decimal


class InventoryService:

    @staticmethod
    async def set_stock(
        session: AsyncSession,
        group_id: int,
        item_name: str,
        quantity: Decimal,
        unit: str = None,
        minimum: Decimal = None,
    ) -> InventoryItem:
        """Crea o actualiza stock de un producto."""
        name_lower = item_name.strip().lower()
        stmt = select(InventoryItem).where(
            InventoryItem.group_id == group_id,
            InventoryItem.item_name == name_lower,
        )
        result = await session.execute(stmt)
        item = result.scalar_one_or_none()

        if item:
            item.current_quantity = quantity
            if unit:
                item.unit = unit
            if minimum is not None:
                item.minimum_quantity = minimum
        else:
            item = InventoryItem(
                group_id=group_id,
                item_name=name_lower,
                current_quantity=quantity,
                unit=unit,
                minimum_quantity=minimum if minimum is not None else Decimal("1"),
            )
            session.add(item)

        await session.commit()
        await session.refresh(item)
        return item

    @staticmethod
    async def use_item(
        session: AsyncSession, group_id: int, item_name: str, quantity: Decimal
    ) -> InventoryItem | None:
        name_lower = item_name.strip().lower()
        stmt = select(InventoryItem).where(
            InventoryItem.group_id == group_id,
            InventoryItem.item_name == name_lower,
        )
        result = await session.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            return None

        new_qty = item.current_quantity - quantity
        item.current_quantity = max(Decimal("0"), new_qty)
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item

    @staticmethod
    async def set_minimum(
        session: AsyncSession, group_id: int, item_name: str, minimum: Decimal
    ) -> InventoryItem | None:
        name_lower = item_name.strip().lower()
        stmt = select(InventoryItem).where(
            InventoryItem.group_id == group_id,
            InventoryItem.item_name == name_lower,
        )
        result = await session.execute(stmt)
        item = result.scalar_one_or_none()
        if item:
            item.minimum_quantity = minimum
            session.add(item)
            await session.commit()
        return item

    @staticmethod
    async def get_inventory(
        session: AsyncSession, group_id: int
    ) -> list[InventoryItem]:
        stmt = (
            select(InventoryItem)
            .where(InventoryItem.group_id == group_id)
            .order_by(InventoryItem.item_name.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_low_stock(
        session: AsyncSession, group_id: int
    ) -> list[InventoryItem]:
        """Retorna productos donde cantidad actual <= mínimo."""
        stmt = (
            select(InventoryItem)
            .where(
                InventoryItem.group_id == group_id,
                InventoryItem.current_quantity <= InventoryItem.minimum_quantity,
            )
            .order_by(InventoryItem.item_name.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()
