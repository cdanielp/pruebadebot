from aiogram import Router, types
from aiogram.filters import Command
from decimal import Decimal, InvalidOperation

from bot.handlers.registration import get_or_create_user_and_group
from bot.services.balance_service import BalanceService
from bot.database import AsyncSessionLocal
from bot.models.domain import User
from sqlalchemy import select

router = Router()


async def _get_names(session, user_ids: list[int]) -> dict[int, str]:
    """Resuelve IDs internos a display_name."""
    if not user_ids:
        return {}
    stmt = select(User.id, User.display_name).where(User.id.in_(user_ids))
    result = await session.execute(stmt)
    return {row.id: row.display_name or f"#{row.id}" for row in result.all()}


@router.message(Command("balance"))
async def cmd_balance(message: types.Message):
    if message.chat.type not in ("group", "supergroup"):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(
        message.from_user, message.chat
    )

    async with AsyncSessionLocal() as session:
        b = await BalanceService.calculate_balance(session, group_db_id)
        if "error" in b:
            return await message.answer(f"⚠️ {b['error']}")
        names = await _get_names(session, b["members"])

    lines = ["⚖️ *Balance actual*\n"]
    for uid, paid in b["totals_paid"].items():
        lines.append(f"👤 {names.get(uid, uid)}: pagó ${paid:.2f}")

    lines.append(f"\n💰 Total compartido: ${b['total_shared']:.2f}")
    lines.append(f"📐 Corresponde a cada uno: ${b['target_per_user']:.2f}")

    if b["debts"]:
        lines.append("\n💸 *Compensaciones necesarias:*")
        for d in b["debts"]:
            lines.append(
                f"  • {names.get(d['from_user'], d['from_user'])} → "
                f"{names.get(d['to_user'], d['to_user'])}: ${d['amount']:.2f}"
            )
    else:
        lines.append("\n✅ ¡Están al día! No hay deudas pendientes.")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("compensar"))
async def cmd_compensar(message: types.Message):
    if message.chat.type not in ("group", "supergroup"):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(
        message.from_user, message.chat
    )

    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Uso: `/compensar monto [nota]`", parse_mode="Markdown")

    try:
        amount = Decimal(args[1])
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        return await message.reply("⚠️ Monto inválido.")

    note = " ".join(args[2:]) if len(args) > 2 else ""

    async with AsyncSessionLocal() as session:
        # Calcular a quién le debe para saber quién recibe
        b = await BalanceService.calculate_balance(session, group_db_id)
        if "error" in b or not b["debts"]:
            return await message.answer("⚠️ No hay deudas activas o el balance no se pudo calcular.")

        # Asumir que quien ejecuta /compensar es el deudor
        debt = next((d for d in b["debts"] if d["from_user"] == user_db_id), None)
        if not debt:
            return await message.answer("ℹ️ No tienes deudas activas en este grupo.")

        settlement = await BalanceService.register_settlement(
            session,
            group_id=group_db_id,
            from_user_id=user_db_id,
            to_user_id=debt["to_user"],
            amount=amount,
            note=note,
        )

    await message.answer(
        f"✅ *Compensación registrada*\n"
        f"💸 Monto: ${amount:.2f}\n"
        f"📝 Nota: {note or 'Sin nota'}",
        parse_mode="Markdown",
    )


@router.message(Command("deudas"))
async def cmd_deudas(message: types.Message):
    if message.chat.type not in ("group", "supergroup"):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(
        message.from_user, message.chat
    )

    async with AsyncSessionLocal() as session:
        history = await BalanceService.get_settlement_history(session, group_db_id)
        if not history:
            return await message.answer("📭 No hay compensaciones registradas.")
        all_ids = set()
        for s in history:
            all_ids.add(s.from_user_id)
            all_ids.add(s.to_user_id)
        names = await _get_names(session, list(all_ids))

    lines = ["💸 *Historial de compensaciones*\n"]
    for s in history:
        lines.append(
            f"• {names.get(s.from_user_id, s.from_user_id)} → "
            f"{names.get(s.to_user_id, s.to_user_id)}: "
            f"${s.amount:.2f}"
            + (f" _{s.note}_" if s.note else "")
            + f" ({s.settlement_date.strftime('%d/%m/%Y')})"
        )

    await message.answer("\n".join(lines), parse_mode="Markdown")
