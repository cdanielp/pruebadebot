from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy import event, text
from bot.config import settings

engine = create_async_engine(settings.database_url, echo=False)

# Activar FOREIGN KEYS en SQLite (crítico para integridad referencial)
if "sqlite" in settings.database_url:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

Base = declarative_base()


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Crea todas las tablas si no existen. Solo para SQLite / MVP local."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
