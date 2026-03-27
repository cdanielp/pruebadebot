from aiogram import Router, F, types
from aiogram.filters import Command
from decimal import Decimal, InvalidOperation

from bot.handlers.registration import get_or_create_user_and_group
from bot.services.shopping_service import ShoppingService
from bot.database import AsyncSessionLocal

router = Router()

PRIORITY_MAP = {"baja": "baja", "normal": "normal", "alta": "alta", "urgente": "urgente"}
PRIORITY_ICONS = {"baja": "🔵", "normal": "⚪", "alta": "🟡", "urgente": "🔴"}
STATUS_ICONS = {"pendiente": "⬜", "urgente": "🔴", "comprado": "✅", "cancelado": "❌", "agotado": "📭"}


def _require_group(message: types.Message) -> bool:
    return message.chat.type in ("group", "supergroup")


def _item_row_keyboard(item_name: str) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[[
        types.InlineKeyboardButton(text="✅ Comprado", callback_data=f"shop_bought:{item_name}"),
        types.InlineKeyboardButton(text="🔴 Urgente", callback_data=f"shop_urgent:{item_name}"),
        types.InlineKeyboardButton(text="❌ Quitar", callback_data=f"shop_remove:{item_name}"),
    ]])


@router.message(Command("agregar"))
async def cmd_agregar(message: types.Message):
    """Uso: /agregar producto [cantidad] [unidad] [prioridad]"""
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)
    args = message.text.split(maxsplit=4)

    if len(args) < 2:
        return await message.reply("Uso: `/agregar producto [cantidad] [unidad] [prioridad]`\nEj: `/agregar leche 2 litros alta`", parse_mode="Markdown")

    item_name = args[1]
    quantity = None
    unit = None
    priority = "normal"

    if len(args) >= 3:
        try:
            quantity = Decimal(args[2])
        except InvalidOperation:
            # Podría ser prioridad directo
            if args[2].lower() in PRIORITY_MAP:
                priority = args[2].lower()

    if len(args) >= 4 and quantity is not None:
        if args[3].lower() in PRIORITY_MAP:
            priority = args[3].lower()
        else:
            unit = args[3]

    if len(args) >= 5 and args[4].lower() in PRIORITY_MAP:
        priority = args[4].lower()

    async with AsyncSessionLocal() as session:
        item, is_dup = await ShoppingService.add_item(
            session, group_db_id, user_db_id,
            item_name=item_name, quantity=quantity, unit=unit, priority=priority
        )

    icon = PRIORITY_ICONS.get(priority, "⚪")

    if is_dup:
        await message.reply(
            f"⚠️ *{item_name}* ya está en la lista como pendiente.\n"
            f"Estado actual: {STATUS_ICONS.get(item.status, '')} {item.status}",
            parse_mode="Markdown",
        )
    else:
        qty_txt = f"{quantity} {unit or ''}".strip() if quantity else ""
        await message.reply(
            f"✅ Agregado: {icon} *{item_name}*" + (f" — {qty_txt}" if qty_txt else ""),
            parse_mode="Markdown",
            reply_markup=_item_row_keyboard(item_name.lower()),
        )


@router.message(Command("lista"))
async def cmd_lista(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        items = await ShoppingService.get_list(session, group_db_id)

    if not items:
        return await message.answer("📭 La lista de compras está vacía.")

    lines = ["🛒 *Lista de compras*\n"]
    for item in items:
        icon = PRIORITY_ICONS.get(item.priority, "⚪")
        status_icon = STATUS_ICONS.get(item.status, "")
        qty_txt = ""
        if item.quantity:
            qty_txt = f" — {item.quantity} {item.unit or ''}".rstrip()
        lines.append(f"{status_icon} {icon} *{item.item_name}*{qty_txt}")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("urgentes"))
async def cmd_urgentes(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        items = await ShoppingService.get_list(session, group_db_id, only_urgent=True)

    if not items:
        return await message.answer("✅ No hay productos urgentes.")

    lines = ["🔴 *Productos urgentes*\n"]
    for item in items:
        qty_txt = f" — {item.quantity} {item.unit or ''}".rstrip() if item.quantity else ""
        lines.append(f"🔴 *{item.item_name}*{qty_txt}")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("comprado"))
async def cmd_comprado(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply("Uso: `/comprado producto`", parse_mode="Markdown")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        item = await ShoppingService.mark_bought(session, group_db_id, args[1])

    if item:
        await message.reply(f"✅ *{item.item_name}* marcado como comprado.", parse_mode="Markdown")
    else:
        await message.reply(f"⚠️ No encontré *{args[1]}* en la lista pendiente.", parse_mode="Markdown")


@router.message(Command("quitar"))
async def cmd_quitar(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply("Uso: `/quitar producto`", parse_mode="Markdown")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        removed = await ShoppingService.remove_item(session, group_db_id, args[1])

    if removed:
        await message.reply(f"❌ *{args[1]}* quitado de la lista.", parse_mode="Markdown")
    else:
        await message.reply(f"⚠️ No encontré *{args[1]}* en la lista pendiente.", parse_mode="Markdown")


# ─── Callbacks de botones en línea ────────────────────────────────────────────

@router.callback_query(F.data.startswith("shop_bought:"))
async def cb_shop_bought(callback: types.CallbackQuery):
    item_name = callback.data.split(":", 1)[1]
    user_db_id, group_db_id = await get_or_create_user_and_group(callback.from_user, callback.message.chat)

    async with AsyncSessionLocal() as session:
        item = await ShoppingService.mark_bought(session, group_db_id, item_name)

    if item:
        await callback.message.edit_text(f"✅ *{item_name}* marcado como comprado.", parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("shop_urgent:"))
async def cb_shop_urgent(callback: types.CallbackQuery):
    item_name = callback.data.split(":", 1)[1]
    user_db_id, group_db_id = await get_or_create_user_and_group(callback.from_user, callback.message.chat)

    async with AsyncSessionLocal() as session:
        item = await ShoppingService.set_urgent(session, group_db_id, item_name)

    if item:
        await callback.message.edit_text(f"🔴 *{item_name}* marcado como urgente.", parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("shop_remove:"))
async def cb_shop_remove(callback: types.CallbackQuery):
    item_name = callback.data.split(":", 1)[1]
    user_db_id, group_db_id = await get_or_create_user_and_group(callback.from_user, callback.message.chat)

    async with AsyncSessionLocal() as session:
        await ShoppingService.remove_item(session, group_db_id, item_name)

    await callback.message.edit_text(f"❌ *{item_name}* quitado de la lista.", parse_mode="Markdown")
    await callback.answer()
