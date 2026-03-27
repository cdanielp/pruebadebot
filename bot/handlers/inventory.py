from aiogram import Router, types
from aiogram.filters import Command
from decimal import Decimal, InvalidOperation

from bot.handlers.registration import get_or_create_user_and_group
from bot.services.inventory_service import InventoryService
from bot.database import AsyncSessionLocal

router = Router()


def _require_group(message: types.Message) -> bool:
    return message.chat.type in ("group", "supergroup")


@router.message(Command("stock"))
async def cmd_stock(message: types.Message):
    """Uso: /stock producto cantidad [unidad] [minimo:N]"""
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    args = message.text.split(maxsplit=4)
    if len(args) < 3:
        return await message.reply("Uso: `/stock producto cantidad [unidad]`\nEj: `/stock arroz 2 kg`", parse_mode="Markdown")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    item_name = args[1]
    try:
        quantity = Decimal(args[2])
    except InvalidOperation:
        return await message.reply("⚠️ Cantidad inválida.")

    unit = args[3] if len(args) > 3 else None

    async with AsyncSessionLocal() as session:
        item = await InventoryService.set_stock(session, group_db_id, item_name, quantity, unit)
        low = item.current_quantity <= item.minimum_quantity

    status = "⚠️ *Bajo mínimo* — considera agregarlo a la lista." if low else "✅ Stock actualizado."
    await message.reply(
        f"📦 *{item_name}*: {quantity} {unit or ''}\n{status}",
        parse_mode="Markdown",
    )


@router.message(Command("usar"))
async def cmd_usar(message: types.Message):
    """Uso: /usar producto cantidad"""
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.reply("Uso: `/usar producto cantidad`\nEj: `/usar papel 1`", parse_mode="Markdown")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    try:
        quantity = Decimal(args[2])
    except InvalidOperation:
        return await message.reply("⚠️ Cantidad inválida.")

    async with AsyncSessionLocal() as session:
        item = await InventoryService.use_item(session, group_db_id, args[1], quantity)

    if not item:
        return await message.reply(f"⚠️ *{args[1]}* no está en el inventario. Usa `/stock` para agregarlo.", parse_mode="Markdown")

    low = item.current_quantity <= item.minimum_quantity
    low_msg = "\n⚠️ *¡Está por acabarse!* Considera agregarlo a la lista." if low else ""

    await message.reply(
        f"📦 *{item.item_name}*: quedan {item.current_quantity} {item.unit or ''}{low_msg}",
        parse_mode="Markdown",
    )


@router.message(Command("inventario"))
async def cmd_inventario(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        items = await InventoryService.get_inventory(session, group_db_id)

    if not items:
        return await message.answer("📭 El inventario está vacío. Usa `/stock producto cantidad` para agregar.")

    lines = ["📦 *Inventario del hogar*\n"]
    for item in items:
        low = item.current_quantity <= item.minimum_quantity
        icon = "⚠️" if low else "✅"
        lines.append(
            f"{icon} *{item.item_name}*: {item.current_quantity} {item.unit or ''} (mín: {item.minimum_quantity})"
        )

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("bajo_minimo"))
async def cmd_bajo_minimo(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        items = await InventoryService.get_low_stock(session, group_db_id)

    if not items:
        return await message.answer("✅ Todo el inventario está sobre el mínimo.")

    lines = ["⚠️ *Productos bajo mínimo*\n"]
    for item in items:
        lines.append(f"🔴 *{item.item_name}*: {item.current_quantity} {item.unit or ''} (mín: {item.minimum_quantity})")

    lines.append("\n💡 Usa `/agregar producto` para pasarlos a la lista de compras.")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("minimo"))
async def cmd_minimo(message: types.Message):
    """Uso: /minimo producto cantidad"""
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.reply("Uso: `/minimo producto cantidad`\nEj: `/minimo papel 2`", parse_mode="Markdown")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    try:
        minimum = Decimal(args[2])
    except InvalidOperation:
        return await message.reply("⚠️ Cantidad inválida.")

    async with AsyncSessionLocal() as session:
        item = await InventoryService.set_minimum(session, group_db_id, args[1], minimum)

    if item:
        await message.reply(f"✅ Mínimo de *{item.item_name}* fijado en {minimum} {item.unit or ''}.", parse_mode="Markdown")
    else:
        await message.reply(f"⚠️ *{args[1]}* no está en el inventario.", parse_mode="Markdown")
