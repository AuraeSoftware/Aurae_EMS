from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import uuid
from datetime import date, timedelta, datetime
from app.database import get_db
from app.models.models import Invoice, Client, Project, InvoiceStatus
from app.schemas.schemas import InvoiceCreate, InvoiceUpdate, InvoiceOut, InvoicePayment
from app.middleware.auth import get_current_user, require_manager_or_admin

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


def gen_invoice_id() -> str:
    now = date.today()
    return f"INV-{now.year}-{uuid.uuid4().hex[:6].upper()}"


async def _enrich_invoice(inv: Invoice, db: AsyncSession) -> InvoiceOut:
    out = InvoiceOut.model_validate(inv)
    if inv.client_id:
        cl_result = await db.execute(select(Client).where(Client.id == inv.client_id))
        cl = cl_result.scalar_one_or_none()
        if cl:
            out.client_name = cl.name
    elif inv.client_name_text:
        out.client_name = inv.client_name_text
    # A Paid invoice is by definition fully settled — always report it as such,
    # even for records marked paid before per-payment tracking existed.
    if out.status == InvoiceStatus.paid:
        out.amount_received = out.total_amount
    return out


@router.get("", response_model=List[InvoiceOut])
async def list_invoices(
    status: Optional[str] = Query(default=None),
    doc_type: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    from sqlalchemy import and_
    query = select(Invoice)
    conditions = []
    if status and status != "all":
        conditions.append(Invoice.status == status)
    if doc_type:
        conditions.append(Invoice.doc_type == doc_type)
    if conditions:
        query = query.where(and_(*conditions))
    result = await db.execute(query.order_by(Invoice.created_at.desc()))
    return [await _enrich_invoice(inv, db) for inv in result.scalars().all()]


@router.post("", response_model=InvoiceOut, status_code=201)
async def create_invoice(
    data: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    gst_amount = round(data.amount * data.gst_rate / 100, 2)
    total = round(data.amount + gst_amount, 2)
    today = date.today()
    inv = Invoice(
        id=gen_invoice_id(),
        client_id=data.client_id,
        project_id=data.project_id,
        project_desc=data.project_desc,
        amount=data.amount,
        gst_amount=gst_amount,
        total_amount=total,
        issue_date=today,
        due_date=today + timedelta(days=data.due_days),
        notes=data.notes,
    )
    db.add(inv)
    await db.flush()
    return await _enrich_invoice(inv, db)


@router.get("/{inv_id}", response_model=InvoiceOut)
async def get_invoice(inv_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Invoice).where(Invoice.id == inv_id))
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return await _enrich_invoice(inv, db)


@router.patch("/{inv_id}", response_model=InvoiceOut)
async def update_invoice(
    inv_id: str,
    data: InvoiceUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    result = await db.execute(select(Invoice).where(Invoice.id == inv_id))
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if data.status:
        inv.status = data.status
        if data.status == InvoiceStatus.paid and not inv.paid_at:
            inv.paid_at = datetime.utcnow()
            # Update client revenue
            if inv.client_id:
                cl_result = await db.execute(select(Client).where(Client.id == inv.client_id))
                cl = cl_result.scalar_one_or_none()
                if cl:
                    cl.total_revenue += inv.total_amount
    if data.notes is not None:
        inv.notes = data.notes
    if data.issue_date is not None:
        inv.issue_date = data.issue_date
    if data.due_date is not None:
        inv.due_date = data.due_date
    if data.client_name_text is not None:
        inv.client_name_text = data.client_name_text
    if data.amount is not None:
        gst_rate = data.gst_rate if data.gst_rate is not None else (round(inv.gst_amount / inv.amount * 100, 2) if inv.amount else 0)
        inv.amount = data.amount
        inv.gst_amount = round(data.amount * gst_rate / 100, 2)
        inv.total_amount = round(data.amount + inv.gst_amount, 2)
    elif data.gst_rate is not None:
        inv.gst_amount = round(inv.amount * data.gst_rate / 100, 2)
        inv.total_amount = round(inv.amount + inv.gst_amount, 2)
    await db.flush()
    return await _enrich_invoice(inv, db)


@router.delete("/{inv_id}", status_code=204)
async def delete_invoice(inv_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_manager_or_admin)):
    result = await db.execute(select(Invoice).where(Invoice.id == inv_id))
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    await db.delete(inv)




@router.post("/from-generator", response_model=InvoiceOut, status_code=201)
async def create_invoice_from_generator(
    data: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Save invoice/quotation generated from the invoice generator page."""
    from app.schemas.schemas import InvoiceCreate
    gst_rate = float(data.get("gst_rate", 0))
    amount = float(data.get("amount", 0))
    gst_amount = round(amount * gst_rate / 100, 2)
    total = round(amount + gst_amount, 2)
    today = date.today()
    doc_type = data.get("doc_type", "Invoice")
    inv_num = data.get("invoice_number") or gen_invoice_id()
    if doc_type == "Quotation" and not inv_num.startswith("QUO-"):
        inv_num = inv_num.replace("INV-", "QUO-", 1)

    # Use the actual Date / Invoice Due values the user set in the generator UI.
    # Previously this always used server-today + a hardcoded 30 days, ignoring
    # whatever the person actually typed — that's what caused due dates to be
    # wildly wrong (e.g. a month later than the invoice PDF itself showed).
    try:
        issue_date = date.fromisoformat(data["invoice_date"]) if data.get("invoice_date") else today
    except (ValueError, KeyError):
        issue_date = today
    try:
        due_date_val = date.fromisoformat(data["due_date"]) if data.get("due_date") else issue_date + timedelta(days=int(data.get("due_days", 30)))
    except (ValueError, KeyError):
        due_date_val = issue_date + timedelta(days=int(data.get("due_days", 30)))

    inv = Invoice(
        id=inv_num,
        client_id=None,
        project_id=None,
        project_desc=data.get("project_desc", ""),
        amount=amount,
        gst_amount=gst_amount,
        total_amount=total,
        issue_date=issue_date,
        due_date=due_date_val,
        notes=data.get("notes", ""),
        doc_type=doc_type,
        client_name_text=data.get("client_name", ""),
    )
    try:
        db.add(inv)
        await db.flush()
    except Exception:
        # Invoice with same ID already exists (re-download) — refresh it with the
        # latest values instead of silently keeping whatever was saved before.
        await db.rollback()
        result = await db.execute(select(Invoice).where(Invoice.id == inv_num))
        existing = result.scalar_one_or_none()
        if not existing:
            raise
        existing.amount = amount
        existing.gst_amount = gst_amount
        existing.total_amount = total
        existing.issue_date = issue_date
        existing.due_date = due_date_val
        existing.project_desc = data.get("project_desc", existing.project_desc)
        existing.notes = data.get("notes", existing.notes)
        existing.client_name_text = data.get("client_name") or existing.client_name_text
        await db.flush()
        inv = existing
    return await _enrich_invoice(inv, db)


@router.post("/{inv_id}/payment", response_model=InvoiceOut)
async def record_payment(
    inv_id: str,
    data: InvoicePayment,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    result = await db.execute(select(Invoice).where(Invoice.id == inv_id))
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be positive")

    was_fully_paid = inv.status == InvoiceStatus.paid
    inv.amount_received = round((inv.amount_received or 0) + data.amount, 2)
    if inv.amount_received > inv.total_amount:
        inv.amount_received = inv.total_amount  # cap — can't receive more than billed

    now_fully_paid = inv.amount_received >= inv.total_amount
    if now_fully_paid and not was_fully_paid:
        inv.status = InvoiceStatus.paid
        inv.paid_at = datetime.utcnow()
        if inv.client_id:
            cl_result = await db.execute(select(Client).where(Client.id == inv.client_id))
            cl = cl_result.scalar_one_or_none()
            if cl:
                cl.total_revenue += inv.total_amount
    elif inv.amount_received > 0:
        inv.status = InvoiceStatus.pending  # keep visibly outstanding until fully paid

    await db.flush()
    return await _enrich_invoice(inv, db)


@router.post("/check-overdue")
async def check_overdue(db: AsyncSession = Depends(get_db), _=Depends(require_manager_or_admin)):
    today = date.today()
    result = await db.execute(
        select(Invoice).where(
            Invoice.status == InvoiceStatus.pending,
            Invoice.due_date < today,
        )
    )
    invoices = result.scalars().all()
    count = 0
    for inv in invoices:
        inv.status = InvoiceStatus.overdue
        count += 1
    return {"updated": count}
