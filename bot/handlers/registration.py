from aiogram import Router, types
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from bot.models.domain import User, Group, GroupMember
from bot.database import AsyncSessionLocal

router = Router()


async def get_or_create_user_and_group(
    telegram_user: types.User, telegram_chat: types.Chat
) -> tuple[int, int | None]:
    """
    Registra usuario y grupo en una sola transacción coherente.
    Retorna (user_db_id, group_db_id | None).
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # --- Usuario ---
            user_stmt = select(User).where(
                User.telegram_user_id == telegram_user.id
            )
            user_res = await session.execute(user_stmt)
            user = user_res.scalar_one_or_none()

            if not user:
                user = User(
                    telegram_user_id=telegram_user.id,
                    display_name=telegram_user.full_name,
                )
                session.add(user)
                await session.flush()
            else:
                # Actualizar nombre si cambió
                if user.display_name != telegram_user.full_name:
                    user.display_name = telegram_user.full_name
                    session.add(user)

            # --- Grupo ---
            group_id = None
            if telegram_chat.type in ("group", "supergroup"):
                group_stmt = select(Group).where(
                    Group.telegram_chat_id == telegram_chat.id
                )
                group_res = await session.execute(group_stmt)
                group = group_res.scalar_one_or_none()

                if not group:
                    group = Group(
                        telegram_chat_id=telegram_chat.id,
                        group_name=telegram_chat.title or "Hogar",
                    )
                    session.add(group)
                    await session.flush()

                group_id = group.id

                # --- Membresía ---
                member_stmt = select(GroupMember).where(
                    GroupMember.group_id == group.id,
                    GroupMember.user_id == user.id,
                )
                member_res = await session.execute(member_stmt)
                member = member_res.scalar_one_or_none()

                if not member:
                    member = GroupMember(
                        group_id=group.id, user_id=user.id, role="admin"
                    )
                    session.add(member)

            # session.begin() hace commit automático al salir del contexto
            return user.id, group_id
