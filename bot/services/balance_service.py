from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from bot.models.domain import Expense, Settlement, GroupMember
from decimal import Decimal


class BalanceService:

    @staticmethod
    async def calculate_balance(session: AsyncSession, group_id: int) -> dict:
        """
        Calcula el balance real considerando:
        - Gastos compartidos (50/50 por defecto)
        - Compensaciones ya registradas (settlements)
        - Sólo miembros activos
        - Orden estable por user_id
        """
        # 1. Miembros activos ordenados de forma estable
        members_stmt = (
            select(GroupMember.user_id)
            .where(
                GroupMember.group_id == group_id,
                GroupMember.is_active == True,
            )
            .order_by(GroupMember.user_id.asc())
        )
        members_res = await session.execute(members_stmt)
        members = [row.user_id for row in members_res.all()]

        if len(members) < 2:
            return {"error": "Se necesitan al menos 2 miembros activos para calcular el balance."}

        # 2. Total pagado por cada usuario en gastos compartidos no saldados
        payments_stmt = (
            select(Expense.paid_by_user_id, func.sum(Expense.amount).label("total_paid"))
            .where(
                Expense.group_id == group_id,
                Expense.shared == True,
                Expense.is_settled == False,
                Expense.split_type == "50_50",
            )
            .group_by(Expense.paid_by_user_id)
        )
        payments_res = await session.execute(payments_stmt)
        payments = {row.paid_by_user_id: Decimal(str(row.total_paid)) for row in payments_res.all()}

        # 3. Compensaciones ya realizadas (reducen la deuda)
        settlements_from_stmt = (
            select(Settlement.from_user_id, func.sum(Settlement.amount).label("total_sent"))
            .where(Settlement.group_id == group_id)
            .group_by(Settlement.from_user_id)
        )
        settlements_to_stmt = (
            select(Settlement.to_user_id, func.sum(Settlement.amount).label("total_received"))
            .where(Settlement.group_id == group_id)
            .group_by(Settlement.to_user_id)
        )
        sent_res = await session.execute(settlements_from_stmt)
        recv_res = await session.execute(settlements_to_stmt)

        sent = {row.from_user_id: Decimal(str(row.total_sent)) for row in sent_res.all()}
        received = {row.to_user_id: Decimal(str(row.total_received)) for row in recv_res.all()}

        # 4. Calcular balance neto por usuario
        # balance_neto = lo_que_pago_en_gastos + lo_que_recibio_en_compensaciones - lo_que_envio_en_compensaciones
        # Si balance_neto > target_per_user => le deben
        # Si balance_neto < target_per_user => debe

        totals = {}
        for uid in members:
            paid = payments.get(uid, Decimal("0"))
            recv = received.get(uid, Decimal("0"))
            snt = sent.get(uid, Decimal("0"))
            totals[uid] = paid + recv - snt

        total_shared = sum(payments.values())
        target_per_user = total_shared / Decimal(str(len(members)))

        net_balances = {uid: totals[uid] - target_per_user for uid in members}

        # 5. Simplificar deudas (para 2 personas es trivial, para N usa algoritmo de simplificación)
        debts = BalanceService._simplify_debts(net_balances)

        return {
            "members": members,
            "totals_paid": {uid: payments.get(uid, Decimal("0")) for uid in members},
            "total_shared": total_shared,
            "target_per_user": target_per_user,
            "net_balances": net_balances,
            "debts": debts,
        }

    @staticmethod
    def _simplify_debts(net_balances: dict) -> list[dict]:
        """
        Simplifica deudas: quien tiene balance negativo debe a quien tiene positivo.
        Funciona para 2 o más usuarios.
        """
        creditors = sorted(
            [(uid, bal) for uid, bal in net_balances.items() if bal > 0],
            key=lambda x: x[1],
            reverse=True,
        )
        debtors = sorted(
            [(uid, abs(bal)) for uid, bal in net_balances.items() if bal < 0],
            key=lambda x: x[1],
            reverse=True,
        )

        debts = []
        i, j = 0, 0
        creditors = [list(c) for c in creditors]
        debtors = [list(d) for d in debtors]

        while i < len(debtors) and j < len(creditors):
            debtor_id, debt_amount = debtors[i]
            creditor_id, credit_amount = creditors[j]

            transfer = min(debt_amount, credit_amount)
            if transfer > Decimal("0.01"):
                debts.append(
                    {"from_user": debtor_id, "to_user": creditor_id, "amount": transfer}
                )

            debtors[i][1] -= transfer
            creditors[j][1] -= transfer

            if debtors[i][1] < Decimal("0.01"):
                i += 1
            if creditors[j][1] < Decimal("0.01"):
                j += 1

        return debts

    @staticmethod
    async def register_settlement(
        session: AsyncSession,
        group_id: int,
        from_user_id: int,
        to_user_id: int,
        amount: Decimal,
        note: str = "",
    ) -> Settlement:
        settlement = Settlement(
            group_id=group_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            amount=amount,
            note=note,
        )
        session.add(settlement)
        await session.commit()
        await session.refresh(settlement)
        return settlement

    @staticmethod
    async def get_settlement_history(
        session: AsyncSession, group_id: int, limit: int = 20
    ) -> list[Settlement]:
        stmt = (
            select(Settlement)
            .where(Settlement.group_id == group_id)
            .order_by(Settlement.settlement_date.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()
