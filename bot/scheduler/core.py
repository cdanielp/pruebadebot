from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from bot.config import settings
import logging

log = logging.getLogger(__name__)

jobstores = {
    "default": SQLAlchemyJobStore(url=settings.scheduler_db_url)
}

scheduler = AsyncIOScheduler(
    jobstores=jobstores,
    timezone=settings.timezone,
)

# Instancia global del bot (se inyecta en main)
_bot_instance = None


def set_bot(bot):
    global _bot_instance
    _bot_instance = bot


async def _send_reminder(chat_id: int, title: str, reminder_id: int):
    """Función que ejecuta el scheduler cuando dispara un recordatorio."""
    if not _bot_instance:
        log.error("Bot no inicializado en scheduler")
        return
    try:
        await _bot_instance.send_message(
            chat_id,
            f"⏰ *Recordatorio*\n\n{title}",
            parse_mode="Markdown",
        )
        # Marcar como completado si era de una sola vez
        from bot.database import AsyncSessionLocal
        from bot.services.reminder_service import ReminderService
        async with AsyncSessionLocal() as session:
            reminder = await session.get(
                __import__("bot.models.domain", fromlist=["Reminder"]).Reminder,
                reminder_id,
            )
            if reminder and reminder.schedule_type == "once":
                await ReminderService.mark_done(session, reminder_id)
    except Exception as e:
        log.error(f"Error enviando recordatorio {reminder_id}: {e}")


def schedule_reminder(reminder) -> bool:
    """Registra un recordatorio en el scheduler según su tipo."""
    job_id = f"reminder_{reminder.id}"

    try:
        if reminder.schedule_type == "once":
            trigger = DateTrigger(run_date=reminder.scheduled_at, timezone=settings.timezone)

        elif reminder.schedule_type == "daily":
            trigger = CronTrigger(
                hour=reminder.scheduled_at.hour,
                minute=reminder.scheduled_at.minute,
                timezone=settings.timezone,
            )

        elif reminder.schedule_type == "weekly":
            trigger = CronTrigger(
                day_of_week=reminder.scheduled_at.weekday(),
                hour=reminder.scheduled_at.hour,
                minute=reminder.scheduled_at.minute,
                timezone=settings.timezone,
            )

        elif reminder.schedule_type == "monthly":
            trigger = CronTrigger(
                day=reminder.scheduled_at.day,
                hour=reminder.scheduled_at.hour,
                minute=reminder.scheduled_at.minute,
                timezone=settings.timezone,
            )
        else:
            return False

        scheduler.add_job(
            _send_reminder,
            trigger=trigger,
            id=job_id,
            args=[reminder.chat_id, reminder.title, reminder.id],
            replace_existing=True,
            misfire_grace_time=3600,
        )
        log.info(f"Recordatorio #{reminder.id} registrado en scheduler")
        return True

    except Exception as e:
        log.error(f"Error registrando recordatorio #{reminder.id}: {e}")
        return False


async def rehidrate_reminders():
    """Al arrancar, rehidratar todos los recordatorios activos desde BD."""
    from bot.database import AsyncSessionLocal
    from bot.services.reminder_service import ReminderService

    try:
        async with AsyncSessionLocal() as session:
            reminders = await ReminderService.get_all_active_for_scheduling(session)

        count = 0
        for reminder in reminders:
            if schedule_reminder(reminder):
                count += 1

        log.info(f"Rehidratados {count} recordatorios desde BD")
    except Exception as e:
        log.error(f"Error rehidratando recordatorios: {e}")


async def send_weekly_summary(group_id: int, chat_id: int):
    """Envía resumen semanal automático al grupo."""
    if not _bot_instance:
        return
    from bot.database import AsyncSessionLocal
    from bot.services.report_service import ReportService

    async with AsyncSessionLocal() as session:
        data = await ReportService.weekly_summary(session, group_id)

    lines = ["📊 *Resumen automático de la semana*\n"]
    lines.append(f"💰 Total gastado: ${data['total_spent']:.2f}")

    if data["top_categories"]:
        top = data["top_categories"][0]
        lines.append(f"📂 Mayor gasto: {top[0]} (${top[1]:.2f})")

    b = data["balance"]
    if "debts" in b and b["debts"]:
        d = b["debts"][0]
        lines.append(f"⚖️ Pendiente: ${d['amount']:.2f}")
    elif "error" not in b:
        lines.append("⚖️ Balance: ¡Al día! ✅")

    try:
        await _bot_instance.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        log.error(f"Error enviando resumen semanal al grupo {group_id}: {e}")


def schedule_weekly_summaries(groups: list[tuple[int, int]]):
    """Programa resúmenes semanales para cada grupo (domingo 20:00)."""
    for group_id, chat_id in groups:
        job_id = f"weekly_summary_{group_id}"
        scheduler.add_job(
            send_weekly_summary,
            CronTrigger(day_of_week=6, hour=20, minute=0, timezone=settings.timezone),
            id=job_id,
            args=[group_id, chat_id],
            replace_existing=True,
        )


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        log.info("Scheduler iniciado.")
