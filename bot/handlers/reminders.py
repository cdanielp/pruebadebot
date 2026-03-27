from aiogram import Router, types
from aiogram.filters import Command
from datetime import datetime, timedelta
import re
import logging

from bot.handlers.registration import get_or_create_user_and_group
from bot.services.reminder_service import ReminderService
from bot.database import AsyncSessionLocal

router = Router()
log = logging.getLogger(__name__)

# Días de la semana en español
DAYS_ES = {
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
    "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}

MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _parse_datetime(text: str) -> tuple[datetime | None, str]:
    """
    Parsea expresiones de tiempo en español.
    Retorna (datetime, schedule_type).
    Ejemplos:
      'mañana 8pm' -> (tomorrow 20:00, 'once')
      'lunes 9am' -> (next monday 09:00, 'once')
      'lunes 9am semanal' -> (next monday 09:00, 'weekly')
      'todos los dias 7am' -> (tomorrow 07:00, 'daily')
    """
    text = text.lower().strip()
    now = datetime.now()
    schedule_type = "once"
    target = None

    # Detectar recurrencia
    if "semanal" in text or "cada semana" in text:
        schedule_type = "weekly"
        text = text.replace("semanal", "").replace("cada semana", "").strip()
    elif "diario" in text or "todos los dias" in text or "todos los días" in text or "diaria" in text:
        schedule_type = "daily"
        text = re.sub(r"todos los d[ií]as|diario|diaria", "", text).strip()
    elif "mensual" in text:
        schedule_type = "monthly"
        text = text.replace("mensual", "").strip()

    # Extraer hora (8pm, 9am, 14:30, 8:00)
    hour_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    hour = 8
    minute = 0
    if hour_match:
        hour = int(hour_match.group(1))
        minute = int(hour_match.group(2) or 0)
        meridian = hour_match.group(3)
        if meridian == "pm" and hour < 12:
            hour += 12
        elif meridian == "am" and hour == 12:
            hour = 0
        text = text[:hour_match.start()].strip()

    # Detectar día relativo
    if "mañana" in text or "manana" in text:
        target = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    elif "hoy" in text:
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
    else:
        # Detectar día de la semana
        for day_name, weekday in DAYS_ES.items():
            if day_name in text:
                days_ahead = (weekday - now.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                target = (now + timedelta(days=days_ahead)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                break

    if not target:
        # Default: mañana a la hora especificada
        target = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)

    return target, schedule_type


@router.message(Command("recordar"))
async def cmd_recordar(message: types.Message):
    """
    Uso: /recordar [mensaje] [mañana|lunes|...] [hora] [semanal|diario]
    Ej: /recordar sacar basura mañana 8pm
    Ej: /recordar pagar internet lunes 9am semanal
    """
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply(
            "Uso: `/recordar mensaje mañana 8pm`\n"
            "O recurrente: `/recordar sacar basura lunes 8am semanal`",
            parse_mode="Markdown",
        )

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)
    chat_id = message.chat.id

    full_text = args[1]

    # Separar el título del tiempo (heurística: todo antes de mañana/hoy/día)
    time_keywords = list(DAYS_ES.keys()) + ["mañana", "manana", "hoy", "todos"]
    title = full_text
    time_part = full_text

    for kw in time_keywords:
        idx = full_text.lower().find(kw)
        if idx > 0:
            title = full_text[:idx].strip()
            time_part = full_text[idx:].strip()
            break

    if not title:
        title = full_text
        time_part = "mañana 8am"

    scheduled_at, schedule_type = _parse_datetime(time_part)

    if schedule_type == "once" and "pm" not in time_part.lower() and "am" not in time_part.lower():
        # Intentar parsear hora de otra manera si no se detectó
        pass

    async with AsyncSessionLocal() as session:
        reminder = await ReminderService.create_reminder(
            session,
            group_id=group_db_id,
            chat_id=chat_id,
            creator_id=user_db_id,
            title=title or full_text,
            scheduled_at=scheduled_at,
            schedule_type=schedule_type,
        )

    # Registrar en el scheduler
    try:
        from bot.scheduler.core import schedule_reminder
        schedule_reminder(reminder)
    except Exception as e:
        log.warning(f"No se pudo registrar en scheduler: {e}")

    type_labels = {"once": "una vez", "daily": "diario", "weekly": "semanal", "monthly": "mensual"}
    await message.reply(
        f"⏰ *Recordatorio creado*\n"
        f"📝 {title or full_text}\n"
        f"📅 {scheduled_at.strftime('%d/%m/%Y %H:%M')}\n"
        f"🔁 Frecuencia: {type_labels.get(schedule_type, schedule_type)}",
        parse_mode="Markdown",
    )


@router.message(Command("recordatorios"))
async def cmd_recordatorios(message: types.Message):
    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)

    if not group_db_id:
        return await message.answer("⚠️ Solo funciona en grupos.")

    async with AsyncSessionLocal() as session:
        reminders = await ReminderService.get_active(session, group_db_id)

    if not reminders:
        return await message.answer("📭 No hay recordatorios activos.")

    lines = ["⏰ *Recordatorios activos*\n"]
    for r in reminders:
        type_icon = {"once": "1️⃣", "daily": "🔁", "weekly": "📆", "monthly": "🗓️"}.get(r.schedule_type, "⏰")
        lines.append(
            f"{type_icon} `#{r.id}` *{r.title}*\n"
            f"   📅 {r.scheduled_at.strftime('%d/%m/%Y %H:%M')}"
        )

    lines.append("\n💡 Usa `/cancelar_recordatorio ID` para cancelar uno.")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("cancelar_recordatorio"))
async def cmd_cancelar_recordatorio(message: types.Message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        return await message.reply("Uso: `/cancelar_recordatorio ID`", parse_mode="Markdown")

    user_db_id, group_db_id = await get_or_create_user_and_group(message.from_user, message.chat)
    reminder_id = int(args[1])

    async with AsyncSessionLocal() as session:
        cancelled = await ReminderService.cancel_reminder(session, reminder_id, group_db_id)

    if cancelled:
        # Quitar del scheduler también
        try:
            from bot.scheduler.core import scheduler
            scheduler.remove_job(f"reminder_{reminder_id}")
        except Exception:
            pass
        await message.reply(f"✅ Recordatorio `#{reminder_id}` cancelado.", parse_mode="Markdown")
    else:
        await message.reply(f"⚠️ No encontré el recordatorio `#{reminder_id}`.", parse_mode="Markdown")
