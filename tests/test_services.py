import pytest
import pytest_asyncio
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# Usar SQLite en memoria para tests
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def session():
    """Sesión de BD en memoria para tests aislados."""
    from bot.database import Base
    # Importar modelos para que Base los registre
    import bot.models.domain  # noqa

    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncTestSession = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with AsyncTestSession() as s:
        yield s

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _create_group_with_members(session: AsyncSession, n_members: int = 2):
    """Helper: crea grupo y N usuarios miembros. Retorna (group_id, [user_ids])."""
    from bot.models.domain import User, Group, GroupMember

    group = Group(telegram_chat_id=-(10000000000 + n_members), group_name="Test Hogar")
    session.add(group)
    await session.flush()

    user_ids = []
    for i in range(n_members):
        user = User(telegram_user_id=100000 + i, display_name=f"Usuario {i+1}")
        session.add(user)
        await session.flush()
        member = GroupMember(group_id=group.id, user_id=user.id, role="admin")
        session.add(member)
        user_ids.append(user.id)

    await session.commit()
    return group.id, user_ids


# ─── Balance ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_balance_u1_paga_todo(session):
    """Si U1 paga 100 y U2 paga 0, U2 debe 50 a U1."""
    from bot.services.expense_service import ExpenseService
    from bot.services.balance_service import BalanceService

    group_id, (u1, u2) = await _create_group_with_members(session, 2)
    await ExpenseService.create_expense(session, group_id, u1, u1, Decimal("100"), "despensa")

    result = await BalanceService.calculate_balance(session, group_id)
    assert "error" not in result
    assert result["total_shared"] == Decimal("100")
    assert result["target_per_user"] == Decimal("50")
    assert len(result["debts"]) == 1
    assert result["debts"][0]["from_user"] == u2
    assert result["debts"][0]["to_user"] == u1
    assert result["debts"][0]["amount"] == Decimal("50")


@pytest.mark.asyncio
async def test_balance_ambos_pagan_igual(session):
    """Si cada uno paga 50, no hay deuda."""
    from bot.services.expense_service import ExpenseService
    from bot.services.balance_service import BalanceService

    group_id, (u1, u2) = await _create_group_with_members(session, 2)
    await ExpenseService.create_expense(session, group_id, u1, u1, Decimal("50"), "despensa")
    await ExpenseService.create_expense(session, group_id, u2, u2, Decimal("50"), "limpieza")

    result = await BalanceService.calculate_balance(session, group_id)
    assert "error" not in result
    assert result["debts"] == []


@pytest.mark.asyncio
async def test_balance_sin_gastos(session):
    """Sin gastos, no debe haber deudas."""
    from bot.services.balance_service import BalanceService

    group_id, _ = await _create_group_with_members(session, 2)
    result = await BalanceService.calculate_balance(session, group_id)
    assert "error" not in result
    assert result["total_shared"] == Decimal("0")
    assert result["debts"] == []


@pytest.mark.asyncio
async def test_balance_con_settlement_reduce_deuda(session):
    """Si U2 debe 50 pero ya compensó 30, debe solo 20."""
    from bot.services.expense_service import ExpenseService
    from bot.services.balance_service import BalanceService

    group_id, (u1, u2) = await _create_group_with_members(session, 2)
    await ExpenseService.create_expense(session, group_id, u1, u1, Decimal("100"), "despensa")
    await BalanceService.register_settlement(session, group_id, u2, u1, Decimal("30"))

    result = await BalanceService.calculate_balance(session, group_id)
    assert len(result["debts"]) == 1
    assert abs(result["debts"][0]["amount"] - Decimal("20")) < Decimal("0.01")


@pytest.mark.asyncio
async def test_balance_solo_un_miembro_da_error(session):
    from bot.services.balance_service import BalanceService
    from bot.models.domain import User, Group, GroupMember

    group = Group(telegram_chat_id=-99999, group_name="Solo")
    session.add(group)
    await session.flush()
    user = User(telegram_user_id=777, display_name="Solitario")
    session.add(user)
    await session.flush()
    session.add(GroupMember(group_id=group.id, user_id=user.id))
    await session.commit()

    result = await BalanceService.calculate_balance(session, group.id)
    assert "error" in result


# ─── Gastos ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_delete_expense_with_audit(session):
    from bot.services.expense_service import ExpenseService
    from bot.models.domain import AuditLog
    from sqlalchemy import select

    group_id, (u1, u2) = await _create_group_with_members(session)
    expense = await ExpenseService.create_expense(session, group_id, u1, u1, Decimal("200"), "hogar")
    assert expense.id is not None

    await ExpenseService.delete_expense(session, expense.id, u1, group_id)

    logs = (await session.execute(select(AuditLog).where(AuditLog.entity_id == expense.id))).scalars().all()
    actions = [l.action for l in logs]
    assert "CREATE" in actions
    assert "DELETE" in actions


@pytest.mark.asyncio
async def test_update_expense(session):
    from bot.services.expense_service import ExpenseService

    group_id, (u1, _) = await _create_group_with_members(session)
    expense = await ExpenseService.create_expense(session, group_id, u1, u1, Decimal("100"), "extras")
    updated = await ExpenseService.update_expense(session, expense.id, u1, group_id, amount=Decimal("150"))
    assert updated.amount == Decimal("150")


@pytest.mark.asyncio
async def test_expense_wrong_group_raises(session):
    from bot.services.expense_service import ExpenseService

    group_id, (u1, _) = await _create_group_with_members(session)
    expense = await ExpenseService.create_expense(session, group_id, u1, u1, Decimal("50"), "antojos")

    with pytest.raises(ValueError):
        await ExpenseService.delete_expense(session, expense.id, u1, group_id + 999)


# ─── Lista de compras ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_shopping_no_duplicate(session):
    from bot.services.shopping_service import ShoppingService
    from bot.models.domain import User, Group, GroupMember

    group = Group(telegram_chat_id=-55555, group_name="Test")
    session.add(group)
    await session.flush()
    user = User(telegram_user_id=999, display_name="Tester")
    session.add(user)
    await session.flush()
    session.add(GroupMember(group_id=group.id, user_id=user.id))
    await session.commit()

    _, is_dup = await ShoppingService.add_item(session, group.id, user.id, "leche")
    assert not is_dup

    _, is_dup2 = await ShoppingService.add_item(session, group.id, user.id, "leche")
    assert is_dup2


@pytest.mark.asyncio
async def test_shopping_mark_bought(session):
    from bot.services.shopping_service import ShoppingService
    from bot.models.domain import User, Group, GroupMember

    group = Group(telegram_chat_id=-66666, group_name="Test2")
    session.add(group)
    await session.flush()
    user = User(telegram_user_id=888, display_name="Tester2")
    session.add(user)
    await session.flush()
    session.add(GroupMember(group_id=group.id, user_id=user.id))
    await session.commit()

    await ShoppingService.add_item(session, group.id, user.id, "huevos")
    bought = await ShoppingService.mark_bought(session, group.id, "huevos")
    assert bought is not None
    assert bought.status == "comprado"

    # Ya no aparece como pendiente
    pending = await ShoppingService.get_list(session, group.id, only_pending=True)
    names = [i.item_name for i in pending]
    assert "huevos" not in names


# ─── Inventario ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_inventory_low_stock_detection(session):
    from bot.services.inventory_service import InventoryService
    from bot.models.domain import Group

    group = Group(telegram_chat_id=-77777, group_name="Inv")
    session.add(group)
    await session.commit()

    await InventoryService.set_stock(session, group.id, "papel", Decimal("3"), "rollos", minimum=Decimal("5"))
    low = await InventoryService.get_low_stock(session, group.id)
    assert any(i.item_name == "papel" for i in low)


@pytest.mark.asyncio
async def test_inventory_use_does_not_go_negative(session):
    from bot.services.inventory_service import InventoryService
    from bot.models.domain import Group

    group = Group(telegram_chat_id=-88888, group_name="Inv2")
    session.add(group)
    await session.commit()

    await InventoryService.set_stock(session, group.id, "aceite", Decimal("1"), "litro")
    item = await InventoryService.use_item(session, group.id, "aceite", Decimal("5"))
    assert item.current_quantity == Decimal("0")
