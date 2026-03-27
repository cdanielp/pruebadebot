from aiogram import Router, types
from aiogram.filters import Command
from decimal import Decimal, InvalidOperation

from bot.handlers.registration import get_or_create_user_and_group
from bot.services.service_manager import ServiceManager
from bot.database import AsyncSessionLocal

router = Router()


def _require_group(message: types.Message) -> bool:
    return message.chat.type in ("group", "supergroup")


@router.message(Command("servicio"))
async def cmd_servicio(message: types.Message):
    """Uso: /servicio nombre monto dia [yo|ambos]"""
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    args = message.text.split(maxsplit=4)
    if len(args) < 4:
        return await message.reply(
            "Uso: `/servicio nombre monto dia [yo|ambos]`\n"
            "Ej: `/servicio internet 600 5 ambos`",
            parse_mode="Markdown",
        )

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    name = args[1]
    try:
        monto = Decimal(args[2])
        day = int(args[3])
        if not 1 <= day <= 31:
            raise ValueError
    except (InvalidOperation, ValueError):
        return await message.reply("⚠️ Monto o día inválido. El día debe ser entre 1 y 31.")

    shared = True
    payer_id = None
    if len(args) == 5:
        who = args[4].lower()
        if who == "yo":
            shared = False
            payer_id = user_db_id
        elif who == "ambos":
            shared = True
        else:
            return await message.reply("⚠️ El último parámetro debe ser `yo` o `ambos`.", parse_mode="Markdown")

    async with AsyncSessionLocal() as session:
        svc = await ServiceManager.create_service(
            session, group_db_id, name, day, monto, payer_id, shared
        )

    shared_txt = "👫 Compartido" if shared else "👤 Personal"
    await message.reply(
        f"✅ *Servicio registrado*\n"
        f"🔌 Nombre: *{name}*\n"
        f"💰 Monto: ${monto:.2f}\n"
        f"📅 Vence el día: {day}\n"
        f"{shared_txt}",
        parse_mode="Markdown",
    )


@router.message(Command("servicios"))
async def cmd_servicios(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        svcs = await ServiceManager.get_services(session, group_db_id)

    if not svcs:
        return await message.answer("📭 No hay servicios registrados. Usa `/servicio nombre monto dia`.")

    lines = ["🔌 *Servicios activos*\n"]
    for s in svcs:
        shared_icon = "👫" if s.shared else "👤"
        paid_txt = f"  _(último pago: {s.last_paid_date.strftime('%d/%m/%Y')})_" if s.last_paid_date else ""
        lines.append(
            f"{shared_icon} *{s.name}* — ${s.estimated_amount:.2f} — día {s.due_day}{paid_txt}"
        )

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("pagado"))
async def cmd_pagado(message: types.Message):
    """Uso: /pagado nombre [monto_real]"""
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        return await message.reply("Uso: `/pagado nombre [monto_real]`\nEj: `/pagado internet 620`", parse_mode="Markdown")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    name = args[1]
    amount = None
    if len(args) == 3:
        try:
            amount = Decimal(args[2])
        except InvalidOperation:
            return await message.reply("⚠️ Monto inválido.")

    async with AsyncSessionLocal() as session:
        # Obtener monto estimado si no se especificó
        if amount is None:
            svcs = await ServiceManager.get_services(session, group_db_id)
            svc_found = next((s for s in svcs if s.name == name.lower()), None)
            if svc_found and svc_found.estimated_amount:
                amount = svc_found.estimated_amount
            else:
                return await message.reply("⚠️ Especifica el monto: `/pagado nombre monto`", parse_mode="Markdown")

        svc, payment = await ServiceManager.mark_paid(session, group_db_id, name, amount, user_db_id)

        # Si el servicio es compartido, registrar como gasto compartido para que afecte el balance
        balance_txt = ""
        if svc and svc.shared:
            from bot.services.expense_service import ExpenseService
            from bot.services.balance_service import BalanceService
            await ExpenseService.create_expense(
                session=session,
                group_id=group_db_id,
                creator_id=user_db_id,
                payer_id=user_db_id,
                amount=amount,
                category="servicios",
                description=f"Pago de {svc.name}",
                shared=True,
            )
            try:
                b = await BalanceService.calculate_balance(session, group_db_id)
                if "debts" in b and b["debts"]:
                    d = b["debts"][0]
                    balance_txt = f"\n⚖️ *Balance:* debe ${d['amount']:.2f} para cuadrar."
                elif "error" not in b:
                    balance_txt = "\n⚖️ *Balance:* Están al día ✅"
            except Exception:
                pass

    if not svc:
        return await message.reply(f"⚠️ No encontré el servicio *{name}*.", parse_mode="Markdown")

    shared_txt = "\n👫 Registrado como gasto compartido." if svc.shared else ""
    await message.reply(
        f"✅ *{svc.name}* marcado como pagado\n"
        f"💰 Monto: ${amount:.2f}\n"
        f"📅 Fecha: {payment.paid_date.strftime('%d/%m/%Y')}"
        f"{shared_txt}{balance_txt}",
        parse_mode="Markdown",
    )


@router.message(Command("proximos_pagos"))
async def cmd_proximos_pagos(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        svcs = await ServiceManager.get_upcoming(session, group_db_id, within_days=7)

    if not svcs:
        return await message.answer("✅ No hay servicios por vencer en los próximos 7 días.")

    lines = ["📅 *Próximos pagos (7 días)*\n"]
    for s in svcs:
        lines.append(f"🔔 *{s.name}* — ${s.estimated_amount:.2f} — día {s.due_day}")

    await message.answer("\n".join(lines), parse_mode="Markdown")
