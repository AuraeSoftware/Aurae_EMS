from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app.models.models import (
    PaymentRequest, Transaction, User, UserRole,
    PaymentRequestStatus, TransactionStatus
)
from app.schemas.schemas import (
    PaymentRequestCreate, PaymentApprovalAction,
    PaymentRequestOut, TransactionOut, BankBalanceOut
)
from app.middleware.auth import get_current_user, require_admin, require_manager_or_admin
from app.services.axis_bank import axis_bank

router = APIRouter(prefix="/api/payments", tags=["payments"])


async def _enrich_pr(pr: PaymentRequest, db: AsyncSession) -> PaymentRequestOut:
    out = PaymentRequestOut.model_validate(pr)
    raiser_result = await db.execute(select(User).where(User.id == pr.raised_by))
    raiser = raiser_result.scalar_one_or_none()
    if raiser:
        out.raiser_name = raiser.name
    if pr.approved_by:
        approver_result = await db.execute(select(User).where(User.id == pr.approved_by))
        approver = approver_result.scalar_one_or_none()
        if approver:
            out.approver_name = approver.name
    return out


# ── Payment Requests ────────────────────────────────────────────────────────────

@router.get("/requests", response_model=List[PaymentRequestOut])
async def list_payment_requests(
    status: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    query = select(PaymentRequest)
    # Employees cannot see payment requests at all
    if current.role == UserRole.employee:
        raise HTTPException(status_code=403, detail="Access denied")
    if current.role == UserRole.manager:
        query = query.where(PaymentRequest.raised_by == current.id)
    if status:
        query = query.where(PaymentRequest.status == status)
    query = query.order_by(PaymentRequest.created_at.desc())
    result = await db.execute(query)
    return [await _enrich_pr(pr, db) for pr in result.scalars().all()]


@router.post("/requests", response_model=PaymentRequestOut, status_code=201)
async def raise_payment_request(
    data: PaymentRequestCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_manager_or_admin),
):
    pr = PaymentRequest(
        raised_by=current.id,
        beneficiary_name=data.beneficiary_name,
        payment_type=data.payment_type,
        amount=data.amount,
        purpose=data.purpose,
        beneficiary_account=data.beneficiary_account,
        beneficiary_ifsc=data.beneficiary_ifsc,
        upi_id=data.upi_id,
        status=PaymentRequestStatus.pending,
    )
    db.add(pr)
    await db.flush()
    return await _enrich_pr(pr, db)


@router.post("/requests/{req_id}/action", response_model=PaymentRequestOut)
async def process_payment_request(
    req_id: int,
    data: PaymentApprovalAction,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_admin),  # Only Admin can approve
):
    result = await db.execute(select(PaymentRequest).where(PaymentRequest.id == req_id))
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="Payment request not found")
    if pr.status != PaymentRequestStatus.pending:
        raise HTTPException(status_code=400, detail=f"Request already {pr.status.value}")

    if data.action == "rejected":
        pr.status = PaymentRequestStatus.rejected
        pr.approved_by = current.id
        pr.rejection_reason = data.reason
        await db.flush()
        return await _enrich_pr(pr, db)

    if data.action != "approved":
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approved' or 'rejected'")

    # Process payment via Axis Bank
    axis_resp = await axis_bank.initiate_payment(
        payment_type=pr.payment_type,
        beneficiary_name=pr.beneficiary_name,
        amount=pr.amount,
        beneficiary_account=pr.beneficiary_account,
        beneficiary_ifsc=pr.beneficiary_ifsc,
        upi_id=pr.upi_id,
        remarks=pr.purpose,
    )

    txn = Transaction(
        reference=axis_resp["reference"],
        payment_type=pr.payment_type,
        beneficiary_name=pr.beneficiary_name,
        beneficiary_account=pr.beneficiary_account,
        beneficiary_ifsc=pr.beneficiary_ifsc,
        upi_id=pr.upi_id,
        amount=pr.amount,
        status=TransactionStatus.success if axis_resp["success"] else TransactionStatus.failed,
        remarks=pr.purpose,
        axis_response=str(axis_resp),
    )
    db.add(txn)
    await db.flush()

    pr.status = PaymentRequestStatus.processed if axis_resp["success"] else PaymentRequestStatus.rejected
    pr.approved_by = current.id
    pr.transaction_id = txn.id
    if not axis_resp["success"]:
        pr.rejection_reason = axis_resp.get("error", "Payment processing failed")
    await db.flush()
    return await _enrich_pr(pr, db)


# ── Transactions ────────────────────────────────────────────────────────────────

@router.get("/transactions", response_model=List[TransactionOut])
async def list_transactions(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    result = await db.execute(select(Transaction).order_by(Transaction.created_at.desc()))
    return [TransactionOut.model_validate(t) for t in result.scalars().all()]


# ── Bank Balance ───────────────────────────────────────────────────────────────

@router.get("/balance", response_model=BankBalanceOut)
async def get_bank_balance(_=Depends(require_admin)):
    data = await axis_bank.get_balance()
    return BankBalanceOut(
        account_number=data.get("account_number", "****"),
        balance=data.get("balance", 0),
        last_refreshed=data.get("last_refreshed", ""),
    )
