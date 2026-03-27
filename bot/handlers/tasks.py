from aiogram import Router, F, types
from aiogram.filters import Command

from bot.handlers.registration import get_or_create_user_and_group
from bot.services.task_service import TaskService
from bot.database import AsyncSessionLocal

router = Router()


def _require_group(message: types.Message) -> bool:
    return message.chat.type in ("group", "supergroup")


def _task_keyboard(task_id: int) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[[
        types.InlineKeyboardButton(text="✅ Hecha", callback_data=f"task_done:{task_id}"),
        types.InlineKeyboardButton(text="🗑️ Cancelar", callback_data=f"task_cancel:{task_id}"),
    ]])


@router.message(Command("tarea"))
async def cmd_tarea(message: types.Message):
    """Uso: /tarea título [descripción]"""
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        return await message.reply("Uso: `/tarea título [descripción opcional]`\nEj: `/tarea limpiar baño sábado por la mañana`", parse_mode="Markdown")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    title = args[1]
    description = args[2] if len(args) > 2 else ""

    async with AsyncSessionLocal() as session:
        task = await TaskService.create_task(
            session, group_db_id, user_db_id, title=title, description=description
        )

    await message.reply(
        f"✅ *Tarea creada* `#{task.id}`\n📋 {task.title}" +
        (f"\n📝 {task.description}" if task.description else ""),
        parse_mode="Markdown",
        reply_markup=_task_keyboard(task.id),
    )


@router.message(Command("pendientes"))
async def cmd_pendientes(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        tasks = await TaskService.get_pending(session, group_db_id)
        overdue = await TaskService.get_overdue(session, group_db_id)

    if not tasks:
        return await message.answer("✅ No hay tareas pendientes.")

    overdue_ids = {t.id for t in overdue}
    lines = ["✅ *Tareas pendientes*\n"]
    for t in tasks:
        icon = "⏰" if t.id in overdue_ids else "📋"
        due_txt = f" — vence {t.due_at.strftime('%d/%m %H:%M')}" if t.due_at else ""
        lines.append(f"{icon} `#{t.id}` *{t.title}*{due_txt}")

    if overdue:
        lines.append(f"\n⏰ {len(overdue)} tarea(s) vencida(s)")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
    )


@router.message(Command("hecha"))
async def cmd_hecha(message: types.Message):
    """Uso: /hecha título o #ID"""
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply("Uso: `/hecha título` o `/hecha #ID`", parse_mode="Markdown")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)
    query = args[1].lstrip("#").strip()

    async with AsyncSessionLocal() as session:
        # Intentar por ID primero
        task = None
        if query.isdigit():
            task = await session.get(__import__('bot.models.domain', fromlist=['Task']).Task, int(query))
            if task and task.group_id != group_db_id:
                task = None
        
        if not task:
            task = await TaskService.find_by_title(session, group_db_id, query)

        if not task:
            return await message.reply(f"⚠️ No encontré la tarea *{query}*.", parse_mode="Markdown")

        task = await TaskService.mark_done(session, task.id, group_db_id, user_db_id)

    await message.reply(f"✅ Tarea *{task.title}* marcada como completada.", parse_mode="Markdown")


# ─── Callbacks ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("task_done:"))
async def cb_task_done(callback: types.CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    user_db_id, group_db_id = await get_or_create_user_and_group(callback.from_user, callback.message.chat)

    async with AsyncSessionLocal() as session:
        task = await TaskService.mark_done(session, task_id, group_db_id, user_db_id)

    if task:
        await callback.message.edit_text(f"✅ Tarea *{task.title}* completada.", parse_mode="Markdown")
    await callback.answer("¡Tarea marcada!")


@router.callback_query(F.data.startswith("task_cancel:"))
async def cb_task_cancel(callback: types.CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    user_db_id, group_db_id = await get_or_create_user_and_group(callback.from_user, callback.message.chat)

    async with AsyncSessionLocal() as session:
        from bot.models.domain import Task
        task = await session.get(Task, task_id)
        if task and task.group_id == group_db_id:
            task.status = "cancelada"
            session.add(task)
            await session.commit()

    await callback.message.edit_text("❌ Tarea cancelada.", parse_mode="Markdown")
    await callback.answer()
