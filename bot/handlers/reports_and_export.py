from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
import os
from datetime import datetime

from bot.handlers.registration import get_or_create_user_and_group
from bot.services.report_service import ReportService
from bot.services.export_service import ExporterService
from bot.services.budget_service import BudgetService
from bot.database import AsyncSessionLocal

router = Router()


def _require_group(message: types.Message) -> bool:
    return message.chat.type in ("group", "supergroup")


# ─── Presupuestos ─────────────────────────────────────────────────────────────

@router.message(Command("presupuesto"))
async def cmd_presupuesto(message: types.Message):
    """Uso: /presupuesto categoría monto"""
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.reply("Uso: `/presupuesto categoría monto`\nEj: `/presupuesto despensa 4000`", parse_mode="Markdown")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    from decimal import Decimal, InvalidOperation
    try:
        limit = Decimal(args[2])
    except InvalidOperation:
        return await message.reply("⚠️ Monto inválido.")

    async with AsyncSessionLocal() as session:
        budget = await BudgetService.set_budget(session, group_db_id, args[1].lower(), limit)

    now = datetime.now()
    await message.reply(
        f"✅ Presupuesto de *{args[1]}* fijado en ${limit:.2f} para {now.strftime('%B %Y')}.",
        parse_mode="Markdown",
    )


@router.message(Command("presupuesto_ver"))
async def cmd_presupuesto_ver(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        budgets = await BudgetService.get_budgets(session, group_db_id)

    if not budgets:
        return await message.answer("📭 No hay presupuestos configurados. Usa `/presupuesto categoría monto`.")

    lines = ["💼 *Presupuestos del mes*\n"]
    for b in budgets:
        bar_filled = int(min(b["pct"], 100) / 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        icon = "🔴" if b["over_budget"] else ("🟡" if b["pct"] >= 80 else "🟢")
        lines.append(
            f"{icon} *{b['category']}*\n"
            f"   [{bar}] {b['pct']:.0f}%\n"
            f"   Gastado: ${b['spent']:.2f} / ${b['limit']:.2f} — Restante: ${b['remaining']:.2f}"
        )

    await message.answer("\n".join(lines), parse_mode="Markdown")


# ─── Reportes ─────────────────────────────────────────────────────────────────

@router.message(Command("resumen_semana"))
async def cmd_resumen_semana(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        data = await ReportService.weekly_summary(session, group_db_id)
        # Resolver nombres
        from bot.models.domain import User
        from sqlalchemy import select as sel
        payer_ids = list(data["by_payer"].keys())
        names = {}
        if payer_ids:
            res = await session.execute(sel(User.id, User.display_name).where(User.id.in_(payer_ids)))
            names = {r.id: r.display_name or f"#{r.id}" for r in res.all()}

    lines = ["📊 *Resumen de la semana*\n"]
    lines.append(f"💰 *Total gastado:* ${data['total_spent']:.2f}\n")

    if data["top_categories"]:
        lines.append("📂 *Top categorías:*")
        for cat, total in data["top_categories"]:
            lines.append(f"  • {cat}: ${total:.2f}")

    if data["by_payer"]:
        lines.append("\n👤 *Pagado por cada uno:*")
        for uid, total in data["by_payer"].items():
            lines.append(f"  • {names.get(uid, uid)}: ${total:.2f}")

    b = data["balance"]
    if "debts" in b and b["debts"]:
        d = b["debts"][0]
        fn = names.get(d['from_user'], d['from_user'])
        lines.append(f"\n⚖️ *Balance:* {fn} debe ${d['amount']:.2f}")
    elif "error" not in b:
        lines.append("\n⚖️ *Balance:* ¡Están al día! ✅")

    if data["urgent_items"]:
        lines.append(f"\n🔴 *Urgentes en lista:* {', '.join(i.item_name for i in data['urgent_items'])}")

    if data["upcoming_services"]:
        lines.append("\n🔔 *Servicios próximos:*")
        for s in data["upcoming_services"]:
            lines.append(f"  • {s.name} — día {s.due_day} — ${s.estimated_amount:.2f}")

    if data["pending_tasks"]:
        lines.append(f"\n📋 *Tareas pendientes:* {len(data['pending_tasks'])}")
        for t in data["pending_tasks"][:3]:
            lines.append(f"  • {t.title}")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("resumen_mes"))
async def cmd_resumen_mes(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        data = await ReportService.monthly_summary(session, group_db_id)

    now = datetime.now()
    lines = [f"📊 *Resumen de {now.strftime('%B %Y')}*\n"]
    lines.append(f"💰 *Total gastado:* ${data['total_spent']:.2f}\n")

    if data["by_category"]:
        lines.append("📂 *Por categoría:*")
        for cat, total in data["by_category"]:
            lines.append(f"  • {cat}: ${total:.2f}")

    b = data["balance"]
    if "debts" in b and b["debts"]:
        d = b["debts"][0]
        lines.append(f"\n⚖️ *Balance:* `{d['from_user']}` debe ${d['amount']:.2f}")
    elif "error" not in b:
        lines.append("\n⚖️ *Balance:* ¡Están al día! ✅")

    await message.answer("\n".join(lines), parse_mode="Markdown")


# ─── Exportación ──────────────────────────────────────────────────────────────

@router.message(Command("exportar_gastos"))
async def cmd_exportar_gastos(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    now = datetime.now()
    async with AsyncSessionLocal() as session:
        path = await ExporterService.export_expenses_csv(session, group_db_id, month=now.month, year=now.year)

    if not path:
        return await message.answer("📭 No hay gastos este mes para exportar.")

    try:
        await message.answer_document(
            FSInputFile(path, filename=f"gastos_{now.strftime('%Y_%m')}.csv"),
            caption=f"📊 Gastos de {now.strftime('%B %Y')}",
        )
    finally:
        ExporterService.cleanup(path)


@router.message(Command("exportar_lista"))
async def cmd_exportar_lista(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        path = await ExporterService.export_shopping_csv(session, group_db_id)

    if not path:
        return await message.answer("📭 La lista está vacía.")

    try:
        await message.answer_document(
            FSInputFile(path, filename="lista_compras.csv"),
            caption="🛒 Lista de compras",
        )
    finally:
        ExporterService.cleanup(path)


@router.message(Command("exportar_inventario"))
async def cmd_exportar_inventario(message: types.Message):
    if not _require_group(message):
        return await message.answer("⚠️ Solo funciona en grupos.")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    async with AsyncSessionLocal() as session:
        path = await ExporterService.export_inventory_csv(session, group_db_id)

    if not path:
        return await message.answer("📭 El inventario está vacío.")

    try:
        await message.answer_document(
            FSInputFile(path, filename="inventario.csv"),
            caption="📦 Inventario del hogar",
        )
    finally:
        ExporterService.cleanup(path)
