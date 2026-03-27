from aiogram import Router, types
from aiogram.filters import Command
from bot.handlers.registration import get_or_create_user_and_group

router = Router()

MENU_TEXT = """
🏠 *Menú principal — Bot del Hogar*

*💰 Gastos*
/gasto `monto categoría [nota]` — Gasto rápido
/gastos_hoy — Ver gastos de hoy
/gastos_semana — Ver gastos de la semana
/gastos_mes — Ver gastos del mes

*⚖️ Balance*
/balance — Ver quién debe qué
/compensar `monto` — Registrar pago de deuda
/deudas — Ver compensaciones anteriores

*🛒 Lista de compras*
/agregar `producto cantidad unidad prioridad` — Agregar producto
/lista — Ver lista pendiente
/urgentes — Ver urgentes
/comprado `producto` — Marcar como comprado
/quitar `producto` — Quitar de la lista

*📦 Inventario*
/stock `producto cantidad unidad` — Actualizar inventario
/usar `producto cantidad` — Descontar del inventario
/inventario — Ver todo el inventario
/bajo_minimo — Ver productos por acabarse
/minimo `producto cantidad` — Fijar mínimo

*🔌 Servicios y pagos fijos*
/servicio `nombre monto dia [yo|ambos]` — Crear servicio
/servicios — Ver servicios activos
/pagado `nombre monto` — Marcar servicio como pagado
/proximos_pagos — Ver próximos a vencer

*💼 Presupuestos*
/presupuesto `categoría monto` — Fijar presupuesto mensual
/presupuesto_ver — Ver avance vs presupuesto

*✅ Tareas*
/tarea `título [día hora]` — Crear tarea
/pendientes — Ver tareas pendientes
/hecha `título o ID` — Marcar tarea completada

*⏰ Recordatorios*
/recordar `mensaje mañana 8pm` — Crear recordatorio
/recordar `mensaje lunes 9am semanal` — Recurrente
/recordatorios — Ver recordatorios activos

*📊 Reportes y exportación*
/resumen_semana — Resumen de la semana
/resumen_mes — Resumen del mes
/exportar\_gastos — Exportar gastos a CSV
/exportar\_lista — Exportar lista de compras
/exportar\_inventario — Exportar inventario

*⚙️ Configuración*
/config — Ver configuración del grupo
/moneda `MXN|USD` — Cambiar moneda
/mi_id — Ver tu ID de Telegram
/id_grupo — Ver ID de este grupo
"""


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.chat.type in ("group", "supergroup"):
        await get_or_create_user_and_group(message.from_user, message.chat)

    await message.answer(
        f"👋 ¡Hola, {message.from_user.first_name}!\n\n"
        "Soy el *Bot del Hogar* 🏠 — tu asistente para gastos, tareas, "
        "despensa y mucho más.\n\n"
        "Usa /menu para ver todos los comandos disponibles.",
        parse_mode="Markdown",
    )


@router.message(Command("help", "menu"))
async def cmd_menu(message: types.Message):
    await message.answer(MENU_TEXT, parse_mode="Markdown")


@router.message(Command("mi_id"))
async def cmd_mi_id(message: types.Message):
    await message.answer(
        f"🪪 Tu ID de Telegram: `{message.from_user.id}`\n"
        f"Nombre: {message.from_user.full_name}",
        parse_mode="Markdown",
    )


@router.message(Command("id_grupo"))
async def cmd_id_grupo(message: types.Message):
    if message.chat.type == "private":
        await message.answer("⚠️ Este comando solo funciona en grupos.")
        return
    await message.answer(
        f"🆔 ID de este grupo: `{message.chat.id}`\n"
        f"Nombre: {message.chat.title}",
        parse_mode="Markdown",
    )
