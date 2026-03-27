import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.database import init_db
from bot.scheduler.core import start_scheduler, set_bot, rehidrate_reminders, schedule_weekly_summaries

# Importar todos los routers
from bot.handlers import (
    start,
    registration,
    expenses,
    balance,
    shopping,
    inventory,
    services_handler,
    tasks,
    reminders,
    reports_and_export,
    config_handler,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


async def main():
    # 1. Base de datos
    await init_db()
    log.info("Base de datos inicializada.")

    # 2. Bot y Dispatcher
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # 3. Registrar routers en orden de prioridad
    dp.include_router(start.router)
    dp.include_router(expenses.router)
    dp.include_router(balance.router)
    dp.include_router(shopping.router)
    dp.include_router(inventory.router)
    dp.include_router(services_handler.router)
    dp.include_router(tasks.router)
    dp.include_router(reminders.router)
    dp.include_router(reports_and_export.router)
    dp.include_router(config_handler.router)

    # 4. Scheduler persistente
    set_bot(bot)
    start_scheduler()
    await rehidrate_reminders()

    # 5. Programar resúmenes semanales para todos los grupos activos
    try:
        from bot.database import AsyncSessionLocal
        from bot.models.domain import Group
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Group.id, Group.telegram_chat_id))
            groups = [(row.id, row.telegram_chat_id) for row in result.all()]
        if groups:
            schedule_weekly_summaries(groups)
            log.info(f"Resúmenes semanales programados para {len(groups)} grupo(s).")
    except Exception as e:
        log.warning(f"No se pudieron programar resúmenes semanales: {e}")

    # 6. Polling
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Bot en ejecución. Esperando mensajes...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        log.info("Bot detenido.")


if __name__ == "__main__":
    asyncio.run(main())
