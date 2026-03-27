from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from bot.models.domain import ShoppingItem
from decimal import Decimal


VALID_PRIORITIES = ("baja", "normal", "alta", "urgente")
VALID_STATUSES = ("pendiente", "urgente", "comprado", "cancelado", "agotado")


class ShoppingService:

    @staticmethod
    async def add_item(
        session: AsyncSession,
        group_id: int,
        creator_id: int,
        item_name: str,
        quantity: Decimal = None,
        unit: str = None,
        priority: str = "normal",
        category: str = None,
    ) -> tuple[ShoppingItem, bool]:
        """
        Agrega producto. Retorna (item, was_duplicate).
        Si ya existe pendiente, retorna el existente con was_duplicate=True.
        """
        name_lower = item_name.strip().lower()

        # Verificar duplicado
        dup_stmt = select(ShoppingItem).where(
            ShoppingItem.group_id == group_id,
            ShoppingItem.item_name == name_lower,
            ShoppingItem.status.in_(("pendiente", "urgente")),
        )
        dup_res = await session.execute(dup_stmt)
        existing = dup_res.scalar_one_or_none()
        if existing:
            return existing, True

        if priority not in VALID_PRIORITIES:
            priority = "normal"

        item = ShoppingItem(
            group_id=group_id,
            item_name=name_lower,
            quantity=quantity,
            unit=unit,
            priority=priority,
            category=category,
            status="urgente" if priority == "urgente" else "pendiente",
            created_by_user_id=creator_id,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item, False

    @staticmethod
    async def get_list(
        session: AsyncSession,
        group_id: int,
        only_pending: bool = True,
        only_urgent: bool = False,
    ) -> list[ShoppingItem]:
        stmt = select(ShoppingItem).where(ShoppingItem.group_id == group_id)
        if only_urgent:
            stmt = stmt.where(ShoppingItem.status == "urgente")
        elif only_pending:
            stmt = stmt.where(ShoppingItem.status.in_(("pendiente", "urgente")))
        stmt = stmt.order_by(
            ShoppingItem.priority.desc(), ShoppingItem.item_name.asc()
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def mark_bought(
        session: AsyncSession, group_id: int, item_name: str
    ) -> ShoppingItem | None:
        stmt = select(ShoppingItem).where(
            ShoppingItem.group_id == group_id,
            ShoppingItem.item_name == item_name.strip().lower(),
            ShoppingItem.status.in_(("pendiente", "urgente")),
        )
        result = await session.execute(stmt)
        item = result.scalar_one_or_none()
        if item:
            item.status = "comprado"
            session.add(item)
            await session.commit()
        return item

    @staticmethod
    async def remove_item(
        session: AsyncSession, group_id: int, item_name: str
    ) -> bool:
        stmt = select(ShoppingItem).where(
            ShoppingItem.group_id == group_id,
            ShoppingItem.item_name == item_name.strip().lower(),
            ShoppingItem.status.in_(("pendiente", "urgente")),
        )
        result = await session.execute(stmt)
        item = result.scalar_one_or_none()
        if item:
            item.status = "cancelado"
            session.add(item)
            await session.commit()
            return True
        return False

    @staticmethod
    async def set_urgent(
        session: AsyncSession, group_id: int, item_name: str
    ) -> ShoppingItem | None:
        stmt = select(ShoppingItem).where(
            ShoppingItem.group_id == group_id,
            ShoppingItem.item_name == item_name.strip().lower(),
            ShoppingItem.status == "pendiente",
        )
        result = await session.execute(stmt)
        item = result.scalar_one_or_none()
        if item:
            item.status = "urgente"
            item.priority = "urgente"
            session.add(item)
            await session.commit()
        return item
