from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from decimal import Decimal, InvalidOperation
import logging

from bot.handlers.registration import get_or_create_user_and_group
from bot.services.expense_service import ExpenseService
from bot.services.balance_service import BalanceService
from bot.database import AsyncSessionLocal
from datetime import datetime, timedelta

router = Router()
log = logging.getLogger(__name__)

CATEGORIES = [
    "despensa", "limpieza", "baño", "farmacia", "comida_fuera",
    "servicios", "transporte", "mascotas", "hogar", "antojos",
    "extras", "salud", "entretenimiento",
]


class FSMGasto(StatesGroup):
    esperando_monto = State()
    esperando_categoria = State()
    esperando_quien_pago = State()
    esperando_es_compartido = State()
    esperando_nota = State()
    confirmando = State()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _require_group(message: types.Message) -> bool:
    return message.chat.type in ("group", "supergroup")


async def _send_balance_snippet(session, group_id: int) -> str:
    try:
        b = await BalanceService.calculate_balance(session, group_id)
        if "error" in b:
            return ""
        if b["debts"]:
            d = b["debts"][0]
            return f"\n⚖️ *Balance:* debe ${d['amount']:.2f} para cuadrar."
        return "\n⚖️ *Balance:* Están al día ✅"
    except Exception:
        return ""


def _expense_keyboard(expense_id: int) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="✏️ Editar monto",
                    callback_data=f"edit_expense:{expense_id}",
                ),
                types.InlineKeyboardButton(
                    text="🗑️ Borrar",
                    callback_data=f"del_expense:{expense_id}",
                ),
            ]
        ]
    )


# ─── Comando rápido ───────────────────────────────────────────────────────────

@router.message(Command("gasto"))
async def cmd_gasto_rapido(message: types.Message):
    """Uso: /gasto 380 despensa yo leche huevos pan"""
    if not _require_group(message):
        return await message.answer("⚠️ Este comando solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(
        message.from_user, message.chat
    )

    args = message.text.split(maxsplit=3)
    if len(args) < 3:
        return await message.reply(
            "Uso: `/gasto monto categoría [nota]`\n"
            "Ej: `/gasto 380 despensa leche huevos pan`",
            parse_mode="Markdown",
        )

    try:
        monto = Decimal(args[1])
        if monto <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        return await message.reply("⚠️ El monto debe ser un número mayor a 0.")

    categoria = args[2].lower()
    descripcion = args[3] if len(args) > 3 else ""

    async with AsyncSessionLocal() as session:
        gasto = await ExpenseService.create_expense(
            session=session,
            group_id=group_db_id,
            creator_id=user_db_id,
            payer_id=user_db_id,
            amount=monto,
            category=categoria,
            description=descripcion,
        )
        balance_txt = await _send_balance_snippet(session, group_db_id)

    await message.reply(
        f"✅ *Gasto registrado*\n"
        f"💰 Monto: ${monto:.2f}\n"
        f"📂 Categoría: {categoria}\n"
        f"📝 Nota: {descripcion or 'Sin nota'}"
        f"{balance_txt}",
        reply_markup=_expense_keyboard(gasto.id),
        parse_mode="Markdown",
    )


# ─── Consultas de gastos ──────────────────────────────────────────────────────

async def _list_expenses(message: types.Message, date_from: datetime, label: str):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(
        message.from_user, message.chat
    )

    async with AsyncSessionLocal() as session:
        expenses = await ExpenseService.get_expenses(
            session, group_db_id, date_from=date_from, limit=30
        )

    if not expenses:
        return await message.answer(f"📭 No hay gastos {label}.")

    total = sum(Decimal(str(e.amount)) for e in expenses)
    lines = [f"📋 *Gastos {label}* (total: ${total:.2f})\n"]
    for e in expenses[:20]:
        shared_icon = "👫" if e.shared else "👤"
        lines.append(
            f"{shared_icon} `#{e.id}` ${e.amount:.2f} — *{e.category}*"
            + (f" _{e.description}_" if e.description else "")
        )
    if len(expenses) > 20:
        lines.append(f"_...y {len(expenses) - 20} más_")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("gastos_hoy"))
async def cmd_gastos_hoy(message: types.Message):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    await _list_expenses(message, today, "de hoy")


@router.message(Command("gastos_semana"))
async def cmd_gastos_semana(message: types.Message):
    week_ago = datetime.now() - timedelta(days=7)
    await _list_expenses(message, week_ago, "de la semana")


@router.message(Command("gastos_mes"))
async def cmd_gastos_mes(message: types.Message):
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    await _list_expenses(message, month_start, "del mes")


# ─── Callbacks de edición / borrado ───────────────────────────────────────────

@router.callback_query(F.data.startswith("del_expense:"))
async def cb_delete_expense(callback: types.CallbackQuery):
    expense_id = int(callback.data.split(":")[1])
    user_db_id, group_db_id = await get_or_create_user_and_group(
        callback.from_user, callback.message.chat
    )

    confirm_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="✅ Sí, borrar",
                    callback_data=f"confirm_del_expense:{expense_id}",
                ),
                types.InlineKeyboardButton(
                    text="❌ Cancelar", callback_data="cancel_action"
                ),
            ]
        ]
    )
    await callback.message.edit_reply_markup(reply_markup=confirm_kb)
    await callback.answer("¿Confirmar borrado?")


@router.callback_query(F.data.startswith("confirm_del_expense:"))
async def cb_confirm_delete(callback: types.CallbackQuery):
    expense_id = int(callback.data.split(":")[1])
    user_db_id, group_db_id = await get_or_create_user_and_group(
        callback.from_user, callback.message.chat
    )

    try:
        async with AsyncSessionLocal() as session:
            await ExpenseService.delete_expense(
                session, expense_id, user_db_id, group_db_id
            )
        await callback.message.edit_text(
            f"🗑️ Gasto `#{expense_id}` eliminado.", parse_mode="Markdown"
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)


@router.callback_query(F.data.startswith("edit_expense:"))
async def cb_edit_expense(callback: types.CallbackQuery, state: FSMContext):
    expense_id = int(callback.data.split(":")[1])
    await state.update_data(editing_expense_id=expense_id)
    await state.set_state(FSMGasto.esperando_monto)
    await callback.message.answer(
        f"✏️ Editando gasto `#{expense_id}`\nEscribe el *nuevo monto*:",
        parse_mode="Markdown",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel_action")]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_action")
async def cb_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🛑 Acción cancelada.")


# ─── FSM: Nuevo gasto guiado ──────────────────────────────────────────────────

def _category_keyboard() -> types.InlineKeyboardMarkup:
    rows = []
    row = []
    for i, cat in enumerate(CATEGORIES):
        row.append(
            types.InlineKeyboardButton(text=cat, callback_data=f"fsm_cat:{cat}")
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [types.InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel_fsm")]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "btn_nuevo_gasto")
async def fsm_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(FSMGasto.esperando_monto)
    await callback.message.answer(
        "💸 *Nuevo gasto*\n\nEscribe el *monto* (ej: 150.50):",
        parse_mode="Markdown",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="❌ Cancelar", callback_data="cancel_fsm")]
            ]
        ),
    )
    await callback.answer()


@router.message(FSMGasto.esperando_monto)
async def fsm_monto(message: types.Message, state: FSMContext):
    data = await state.get_data()
    editing_id = data.get("editing_expense_id")

    try:
        monto = Decimal(message.text.strip().replace(",", "."))
        if monto <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        return await message.reply("⚠️ Monto inválido. Escribe un número mayor a 0.")

    await state.update_data(monto=str(monto))

    if editing_id:
        # Modo edición: solo actualizar monto
        user_db_id, group_db_id = await get_or_create_user_and_group(
            message.from_user, message.chat
        )
        async with AsyncSessionLocal() as session:
            await ExpenseService.update_expense(
                session, editing_id, user_db_id, group_db_id, amount=monto
            )
        await state.clear()
        return await message.answer(
            f"✅ Gasto `#{editing_id}` actualizado a ${monto:.2f}",
            parse_mode="Markdown",
        )

    await state.set_state(FSMGasto.esperando_categoria)
    await message.answer(
        f"✅ Monto: ${monto:.2f}\n\n📂 Elige la *categoría*:",
        parse_mode="Markdown",
        reply_markup=_category_keyboard(),
    )


@router.callback_query(F.data.startswith("fsm_cat:"))
async def fsm_categoria(callback: types.CallbackQuery, state: FSMContext):
    categoria = callback.data.split(":")[1]
    await state.update_data(categoria=categoria)
    await state.set_state(FSMGasto.esperando_nota)
    await callback.message.answer(
        f"✅ Categoría: *{categoria}*\n\n📝 Agrega una *nota* (o escribe `-` para omitir):",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(FSMGasto.esperando_nota)
async def fsm_nota(message: types.Message, state: FSMContext):
    nota = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(nota=nota)
    data = await state.get_data()

    confirm_kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="✅ Confirmar", callback_data="fsm_confirm"
                ),
                types.InlineKeyboardButton(
                    text="❌ Cancelar", callback_data="cancel_fsm"
                ),
            ]
        ]
    )
    await state.set_state(FSMGasto.confirmando)
    await message.answer(
        f"📋 *Resumen del gasto*\n"
        f"💰 Monto: ${Decimal(data['monto']):.2f}\n"
        f"📂 Categoría: {data['categoria']}\n"
        f"📝 Nota: {nota or 'Sin nota'}\n\n"
        f"¿Confirmamos?",
        parse_mode="Markdown",
        reply_markup=confirm_kb,
    )


@router.callback_query(F.data == "fsm_confirm")
async def fsm_confirmar(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_db_id, group_db_id = await get_or_create_user_and_group(
        callback.from_user, callback.message.chat
    )

    if not group_db_id:
        await callback.answer("⚠️ Solo funciona en grupos.", show_alert=True)
        await state.clear()
        return

    async with AsyncSessionLocal() as session:
        gasto = await ExpenseService.create_expense(
            session=session,
            group_id=group_db_id,
            creator_id=user_db_id,
            payer_id=user_db_id,
            amount=Decimal(data["monto"]),
            category=data["categoria"],
            description=data.get("nota", ""),
        )
        balance_txt = await _send_balance_snippet(session, group_db_id)

    await state.clear()
    await callback.message.edit_text(
        f"✅ *Gasto guardado*\n"
        f"💰 ${Decimal(data['monto']):.2f} — {data['categoria']}"
        f"{balance_txt}",
        reply_markup=_expense_keyboard(gasto.id),
        parse_mode="Markdown",
    )
    await callback.answer("¡Listo!")


@router.callback_query(F.data == "cancel_fsm")
async def fsm_cancelar(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🛑 Gasto cancelado.")
