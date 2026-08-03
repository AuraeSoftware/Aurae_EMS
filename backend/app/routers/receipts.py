import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.models import Receipt, User
from app.schemas.schemas import ReceiptCreate, ReceiptUpdate, ReceiptOut
from app.middleware.auth import require_manager_or_admin

router = APIRouter(prefix="/api/receipts", tags=["receipts"])


def _gen_receipt_id() -> str:
    yr = date.today().strftime("%y")
    return f"RCP-{yr}-{uuid.uuid4().hex[:5].upper()}"


async def _enrich(r: Receipt, db: AsyncSession) -> ReceiptOut:
    out = ReceiptOut.model_validate(r)
    if r.created_by:
        u_result = await db.execute(select(User).where(User.id == r.created_by))
        u = u_result.scalar_one_or_none()
        if u:
            out.created_by_name = u.name
    return out


@router.get("", response_model=list[ReceiptOut])
async def list_receipts(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    query = select(Receipt).order_by(Receipt.payment_date.desc(), Receipt.created_at.desc())
    result = await db.execute(query)
    receipts = result.scalars().all()
    if from_date:
        receipts = [r for r in receipts if r.payment_date >= from_date]
    if to_date:
        receipts = [r for r in receipts if r.payment_date <= to_date]
    return [await _enrich(r, db) for r in receipts]


@router.post("", response_model=ReceiptOut, status_code=201)
async def create_receipt(
    data: ReceiptCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_manager_or_admin),
):
    receipt = Receipt(
        id=_gen_receipt_id(),
        payee_name=data.payee_name,
        purpose=data.purpose,
        amount=data.amount,
        payment_date=data.payment_date,
        payment_method=data.payment_method,
        reference_no=data.reference_no,
        notes=data.notes,
        created_by=current.id,
    )
    db.add(receipt)
    await db.flush()
    return await _enrich(receipt, db)


@router.patch("/{receipt_id}", response_model=ReceiptOut)
async def update_receipt(
    receipt_id: str,
    data: ReceiptUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    result = await db.execute(select(Receipt).where(Receipt.id == receipt_id))
    receipt = result.scalar_one_or_none()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(receipt, field, value)
    await db.flush()
    return await _enrich(receipt, db)


@router.delete("/{receipt_id}", status_code=204)
async def delete_receipt(
    receipt_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    result = await db.execute(select(Receipt).where(Receipt.id == receipt_id))
    receipt = result.scalar_one_or_none()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    await db.delete(receipt)
    await db.flush()
