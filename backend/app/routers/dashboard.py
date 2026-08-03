from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import date
from app.database import get_db
from app.models.models import (
    Employee, Project, Invoice, Attendance, Leave,
    AttendanceStatus, InvoiceStatus, LeaveStatus, PaymentRequest,
    PaymentRequestStatus, User, UserRole
)
from app.schemas.schemas import DashboardStats
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    today = date.today()

    # Monthly revenue (paid invoices current month)
    inv_result = await db.execute(select(Invoice).where(Invoice.status == InvoiceStatus.paid))
    paid_invoices = inv_result.scalars().all()
    monthly_revenue = sum(
        i.total_amount for i in paid_invoices
        if i.paid_at and i.paid_at.month == today.month and i.paid_at.year == today.year
    )

    # Active projects
    proj_result = await db.execute(select(func.count()).select_from(Project).where(Project.status == "active"))
    active_projects = proj_result.scalar() or 0

    # Total employees
    emp_result = await db.execute(select(func.count()).select_from(Employee).where(Employee.is_active == True))
    total_employees = emp_result.scalar() or 0

    # Pending invoices
    pend_result = await db.execute(
        select(func.count()).select_from(Invoice).where(Invoice.status == InvoiceStatus.pending)
    )
    pending_invoices = pend_result.scalar() or 0

    # Overdue invoices
    ovd_result = await db.execute(
        select(func.count()).select_from(Invoice).where(Invoice.status == InvoiceStatus.overdue)
    )
    overdue_invoices = ovd_result.scalar() or 0

    # Today attendance
    att_result = await db.execute(select(Attendance).where(Attendance.date == today))
    att_records = att_result.scalars().all()
    present_today = sum(1 for a in att_records if a.status in (AttendanceStatus.present, AttendanceStatus.late))
    on_leave_today = sum(1 for a in att_records if a.status == AttendanceStatus.leave)

    # Pending leaves
    lv_result = await db.execute(
        select(func.count()).select_from(Leave).where(Leave.status == LeaveStatus.pending)
    )
    pending_leaves = lv_result.scalar() or 0

    # Pending payment requests
    pr_result = await db.execute(
        select(func.count()).select_from(PaymentRequest).where(PaymentRequest.status == PaymentRequestStatus.pending)
    )
    pending_payment_requests = pr_result.scalar() or 0

    return DashboardStats(
        monthly_revenue=monthly_revenue,
        active_projects=active_projects,
        total_employees=total_employees,
        pending_invoices=pending_invoices,
        overdue_invoices=overdue_invoices,
        present_today=present_today,
        on_leave_today=on_leave_today,
        pending_leaves=pending_leaves,
        pending_payment_requests=pending_payment_requests,
    )


@router.get("/activity")
async def recent_activity(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Recent activity feed — employees see only their own activities"""
    activities = []

    if current.role == UserRole.employee:
        # Employee: show only THEIR OWN attendance, leave, and task events
        emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
        emp = emp_result.scalar_one_or_none()
        if emp:
            # Their leave requests
            lv_result = await db.execute(
                select(Leave).where(Leave.employee_id == emp.id).order_by(Leave.created_at.desc()).limit(5)
            )
            for lv in lv_result.scalars().all():
                activities.append({
                    "time": lv.created_at.strftime("%b %d, %H:%M"),
                    "text": f"Leave request {lv.status} ({lv.leave_type})",
                    "type": "leave",
                })
            # Their recent attendance
            from app.models.models import Attendance
            att_result = await db.execute(
                select(Attendance).where(Attendance.employee_id == emp.id)
                .order_by(Attendance.date.desc()).limit(3)
            )
            for att in att_result.scalars().all():
                if att.clock_in:
                    activities.append({
                        "time": att.date.strftime("%b %d"),
                        "text": f"Clocked in at {att.clock_in[:5]} — {att.status.value}",
                        "type": "attendance",
                    })
    else:
        # Manager / Admin: show all org-level events
        lv_result = await db.execute(
            select(Leave).where(Leave.status == LeaveStatus.approved).order_by(Leave.created_at.desc()).limit(3)
        )
        for lv in lv_result.scalars().all():
            emp_res = await db.execute(select(Employee).where(Employee.id == lv.employee_id))
            emp = emp_res.scalar_one_or_none()
            activities.append({
                "time": lv.created_at.strftime("%b %d, %H:%M"),
                "text": f"Leave approved for {emp.name if emp else lv.employee_id}",
                "type": "leave",
            })

        inv_result = await db.execute(
            select(Invoice).where(Invoice.status == InvoiceStatus.paid).order_by(Invoice.paid_at.desc()).limit(3)
        )
        for inv in inv_result.scalars().all():
            if inv.doc_type == "Quotation":
                label = f"Quotation {inv.id} accepted — ₹{inv.total_amount:,.0f}"
            else:
                label = f"Invoice {inv.id} paid — ₹{inv.total_amount:,.0f}"
            activities.append({
                "time": inv.paid_at.strftime("%b %d") if inv.paid_at else "",
                "text": label,
                "type": "payment",
            })

        proj_result = await db.execute(
            select(Project).order_by(Project.created_at.desc()).limit(3)
        )
        for proj in proj_result.scalars().all():
            activities.append({
                "time": proj.created_at.strftime("%b %d"),
                "text": f"Project '{proj.name}' created",
                "type": "project",
            })

    return sorted(activities, key=lambda x: x["time"], reverse=True)[:8]


@router.get("/revenue-chart")
async def revenue_chart(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Monthly revenue data for last 6 months"""
    from datetime import timedelta
    from collections import defaultdict

    inv_result = await db.execute(select(Invoice).where(Invoice.status == InvoiceStatus.paid))
    invoices = inv_result.scalars().all()

    monthly = defaultdict(float)
    for inv in invoices:
        if inv.paid_at:
            key = inv.paid_at.strftime("%b %Y")
            monthly[key] += inv.total_amount

    today = date.today()
    labels = []
    data = []
    for i in range(5, -1, -1):
        d = today.replace(day=1)
        for _ in range(i):
            if d.month == 1:
                d = d.replace(year=d.year - 1, month=12)
            else:
                d = d.replace(month=d.month - 1)
        label = d.strftime("%b")
        labels.append(label)
        key = d.strftime("%b %Y")
        data.append(monthly.get(key, 0))

    return {"labels": labels, "data": data}
