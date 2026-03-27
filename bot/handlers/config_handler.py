from aiogram import Router, types
from aiogram.filters import Command

from bot.handlers.registration import get_or_create_user_and_group
from bot.database import AsyncSessionLocal
from bot.models.domain import Group
from sqlalchemy import select

router = Router()


@router.message(Command("config"))
async def cmd_config(message: types.Message):
    if message.chat.type not in ("group", "supergroup"):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        stmt = select(Group).where(Group.id == group_db_id)
        result = await session.execute(stmt)
        group = result.scalar_one_or_none()

    if not group:
        return await message.answer("⚠️ Grupo no registrado.")

    await message.answer(
        f"⚙️ *Configuración del grupo*\n\n"
        f"🏠 Nombre: {group.group_name}\n"
        f"💱 Moneda: {group.currency}\n"
        f"⚖️ Modo balance: {group.balance_mode}\n\n"
        f"*Comandos disponibles:*\n"
        f"/moneda `MXN|USD|EUR` — Cambiar moneda\n"
        f"/mi_id — Ver tu ID de Telegram\n"
        f"/id_grupo — Ver ID de este grupo",
        parse_mode="Markdown",
    )


@router.message(Command("moneda"))
async def cmd_moneda(message: types.Message):
    if message.chat.type not in ("group", "supergroup"):
        return await message.answer("⚠️ Solo funciona en grupos.")

    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Uso: `/moneda MXN`", parse_mode="Markdown")

    currency = args[1].upper()
    if currency not in ("MXN", "USD", "EUR", "COP", "ARS", "CLP", "PEN"):
        return await message.reply("⚠️ Moneda no soportada. Usa MXN, USD, EUR, etc.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        stmt = select(Group).where(Group.id == group_db_id)
        result = await session.execute(stmt)
        group = result.scalar_one_or_none()
        if group:
            group.currency = currency
            session.add(group)
            await session.commit()

    await message.reply(f"✅ Moneda cambiada a *{currency}*.", parse_mode="Markdown")
