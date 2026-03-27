from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, DateTime,
    ForeignKey, Numeric, Text, CheckConstraint, UniqueConstraint, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from bot.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    display_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    memberships = relationship("GroupMember", back_populates="user", cascade="all, delete-orphan")


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    telegram_chat_id = Column(BigInteger, unique=True, nullable=False, index=True)
    group_name = Column(String(255))
    currency = Column(String(10), default="MXN")
    balance_mode = Column(String(20), default="50_50")
    week_summary_day = Column(Integer, default=6)   # 6 = domingo
    week_summary_hour = Column(Integer, default=20)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")


class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), default="admin")
    is_active = Column(Boolean, default=True)

    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_member"),
        CheckConstraint("role IN ('admin', 'member')", name="check_group_member_role"),
    )


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    paid_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    category = Column(String(100), nullable=False, index=True)
    description = Column(Text)
    shared = Column(Boolean, default=True)
    split_type = Column(String(50), default="50_50")
    expense_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    is_settled = Column(Boolean, default=False)
    receipt_file_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("amount > 0", name="check_expense_amount_positive"),
        CheckConstraint("split_type IN ('50_50', 'custom', 'individual')", name="check_split_type"),
    )


class Settlement(Base):
    """Compensaciones de balance entre miembros."""
    __tablename__ = "settlements"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    from_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    note = Column(Text, nullable=True)
    settlement_date = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("amount > 0", name="check_settlement_amount_positive"),
        CheckConstraint("from_user_id != to_user_id", name="check_settlement_different_users"),
    )


class ShoppingItem(Base):
    __tablename__ = "shopping_items"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    item_name = Column(String(255), nullable=False)
    quantity = Column(Numeric(10, 2), nullable=True)
    unit = Column(String(50), nullable=True)
    category = Column(String(100), nullable=True)
    priority = Column(String(20), default="normal")
    status = Column(String(20), default="pendiente")
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("priority IN ('baja', 'normal', 'alta', 'urgente')", name="check_shopping_priority"),
        CheckConstraint("status IN ('pendiente', 'urgente', 'comprado', 'cancelado', 'agotado')", name="check_shopping_status"),
    )


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    item_name = Column(String(255), nullable=False)
    current_quantity = Column(Numeric(10, 2), nullable=False, default=0)
    unit = Column(String(50), nullable=True)
    minimum_quantity = Column(Numeric(10, 2), nullable=False, default=1)
    category = Column(String(100), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("group_id", "item_name", name="uq_inventory_group_item"),
        CheckConstraint("current_quantity >= 0", name="check_inventory_quantity_non_negative"),
        CheckConstraint("minimum_quantity >= 0", name="check_inventory_minimum_non_negative"),
    )


class Service(Base):
    """Pagos fijos recurrentes (luz, internet, etc.)."""
    __tablename__ = "services"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    estimated_amount = Column(Numeric(12, 2), nullable=True)
    due_day = Column(Integer, nullable=False)
    paid_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    shared = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    last_paid_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    payments = relationship("ServicePayment", back_populates="service", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("due_day >= 1 AND due_day <= 31", name="check_service_due_day"),
        UniqueConstraint("group_id", "name", name="uq_service_group_name"),
    )


class ServicePayment(Base):
    __tablename__ = "service_payments"

    id = Column(Integer, primary_key=True)
    service_id = Column(Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_paid = Column(Numeric(12, 2), nullable=False)
    paid_date = Column(DateTime(timezone=True), server_default=func.now())
    paid_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note = Column(Text, nullable=True)

    service = relationship("Service", back_populates="payments")


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(100), nullable=False)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    monthly_limit = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("group_id", "category", "month", "year", name="uq_budget_group_cat_period"),
        CheckConstraint("monthly_limit > 0", name="check_budget_limit_positive"),
        CheckConstraint("month >= 1 AND month <= 12", name="check_budget_month"),
    )


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    schedule_type = Column(String(20), default="once")
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    recurrence_rule = Column(String(100), nullable=True)
    chat_id = Column(BigInteger, nullable=False)
    status = Column(String(20), default="activo")
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("schedule_type IN ('once', 'daily', 'weekly', 'monthly')", name="check_reminder_schedule_type"),
        CheckConstraint("status IN ('activo', 'completado', 'cancelado')", name="check_reminder_status"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    assigned_to_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    recurrence_rule = Column(String(100), nullable=True)
    status = Column(String(20), default="pendiente")
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('pendiente', 'en_progreso', 'completada', 'cancelada')", name="check_task_status"),
    )


class MealPlan(Base):
    __tablename__ = "meal_plan"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_date = Column(DateTime(timezone=True), nullable=False)
    meal_name = Column(String(255), nullable=False)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        UniqueConstraint("group_id", "plan_date", name="uq_meal_plan_group_date"),
    )


class WishlistItem(Base):
    __tablename__ = "wishlist_items"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    item_name = Column(String(255), nullable=False)
    priority = Column(String(20), default="baja")
    estimated_cost = Column(Numeric(12, 2), nullable=True)
    note = Column(Text, nullable=True)
    status = Column(String(20), default="deseado")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("priority IN ('baja', 'media', 'alta')", name="check_wishlist_priority"),
        CheckConstraint("status IN ('deseado', 'comprado', 'descartado')", name="check_wishlist_status"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(Integer, nullable=False)
    action = Column(String(50), nullable=False)
    before_json = Column(JSON, nullable=True)
    after_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("action IN ('CREATE', 'UPDATE', 'DELETE')", name="check_audit_action"),
    )
