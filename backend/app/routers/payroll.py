from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app.models.models import Payroll, Employee, PayrollStatus, Transaction, TransactionStatus, Attendance, AttendanceStatus, Leave, LeaveStatus, LeaveType
from app.schemas.schemas import PayrollOut, RunPayrollRequest
from app.middleware.auth import require_admin, require_manager_or_admin, get_current_user
from app.services.axis_bank import axis_bank

router = APIRouter(prefix="/api/payroll", tags=["payroll"])

CL_PER_MONTH = 1
LATE_LOP_THRESHOLD = 4


async def _enrich_payroll(p: Payroll, db: AsyncSession) -> PayrollOut:
    out = PayrollOut.model_validate(p)
    emp_result = await db.execute(select(Employee).where(Employee.id == p.employee_id))
    emp = emp_result.scalar_one_or_none()
    if emp:
        out.employee_name = emp.name
        out.employee_role = emp.role
    return out


async def _calc_lop(emp_id: str, month: int, year: int, basic_salary: float, db: AsyncSession) -> dict:
    """Calculate Loss of Pay deductions based on HR policy.

    Unified rule (matches the Attendance Report and payslip display):
      - Absent + On Leave (any approved leave type) combined: 1 day/month is free,
        everything beyond that is LOP. (Approving ANY leave type marks Attendance
        as 'leave' for those days — see leaves.py — so this already covers CL/
        sick/permission together, not just Casual Leave.)
      - Late: every 4 late clock-ins = 0.5 day LOP
      - Half-day (clocked in after 1:30 PM): 0.5 day LOP each
    """
    # Get attendance for month
    att_result = await db.execute(
        select(Attendance).where(
            and_(
                Attendance.employee_id == emp_id,
                func.extract("month", Attendance.date) == month,
                func.extract("year", Attendance.date) == year,
            )
        )
    )
    records = att_result.scalars().all()
    late_count = sum(1 for r in records if r.status == AttendanceStatus.late)
    half_day_count = sum(1 for r in records if r.status == AttendanceStatus.half_day)
    on_leave_count = sum(1 for r in records if r.status == AttendanceStatus.leave)
    present_count = sum(1 for r in records if r.status in (AttendanceStatus.present, AttendanceStatus.late, AttendanceStatus.half_day, AttendanceStatus.wfh))

    # CL taken this month (kept for display purposes only — no longer drives LOP directly,
    # since the combined Absent+OnLeave rule below already covers all leave types)
    leave_result = await db.execute(
        select(Leave).where(
            and_(
                Leave.employee_id == emp_id,
                Leave.leave_type == LeaveType.casual,
                Leave.status == LeaveStatus.approved,
                func.extract("month", Leave.from_date) == month,
                func.extract("year", Leave.from_date) == year,
            )
        )
    )
    leaves = leave_result.scalars().all()
    cl_taken = sum((l.to_date - l.from_date).days + 1 for l in leaves)

    # Working days in month (Mon-Sat, excluding Sundays)
    import calendar
    _, days_in_month = calendar.monthrange(year, month)
    working_days = 0
    for day in range(1, days_in_month + 1):
        if datetime(year, month, day).weekday() < 6:  # 0-5 = Mon-Sat
            working_days += 1

    per_day_salary = basic_salary / working_days if working_days > 0 else 0

    absent_count = max(0, working_days - present_count - on_leave_count)
    late_lop_days = (late_count // LATE_LOP_THRESHOLD) * 0.5
    half_day_lop_days = half_day_count * 0.5
    absent_leave_lop_days = max(0, (absent_count + on_leave_count) - 1)
    total_lop_days = late_lop_days + half_day_lop_days + absent_leave_lop_days
    lop_amount = round(per_day_salary * total_lop_days, 2)

    return {
        "late_count": late_count,
        "half_day_count": half_day_count,
        "absent_count": absent_count,
        "on_leave_count": on_leave_count,
        "cl_taken": cl_taken,
        "late_lop_days": late_lop_days,
        "half_day_lop_days": half_day_lop_days,
        "absent_leave_lop_days": absent_leave_lop_days,
        "total_lop_days": total_lop_days,
        "lop_amount": lop_amount,
        "working_days": working_days,
        "per_day_salary": round(per_day_salary, 2),
    }


@router.get("/my", response_model=List[PayrollOut])
async def my_payroll(
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    """Employee fetches their own payroll/payslip records."""
    emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
    emp = emp_result.scalar_one_or_none()
    if not emp:
        return []
    result = await db.execute(
        select(Payroll).where(Payroll.employee_id == emp.id).order_by(Payroll.year.desc(), Payroll.month.desc())
    )
    return [await _enrich_payroll(p, db) for p in result.scalars().all()]


@router.get("", response_model=List[PayrollOut])
async def list_payroll(
    month: Optional[int] = Query(default=None),
    year: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    query = select(Payroll)
    if month:
        query = query.where(Payroll.month == month)
    if year:
        query = query.where(Payroll.year == year)
    result = await db.execute(query.order_by(Payroll.year.desc(), Payroll.month.desc()))
    return [await _enrich_payroll(p, db) for p in result.scalars().all()]


@router.post("/generate", response_model=List[PayrollOut])
async def generate_payroll(
    data: RunPayrollRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    """Generate payroll with CL and late-deduction HR policy applied."""
    emp_query = select(Employee).where(Employee.is_active == True)
    if data.employee_ids:
        emp_query = emp_query.where(Employee.id.in_(data.employee_ids))
    emp_result = await db.execute(emp_query)
    employees = emp_result.scalars().all()

    results = []
    for emp in employees:
        existing = await db.execute(
            select(Payroll).where(
                and_(
                    Payroll.employee_id == emp.id,
                    Payroll.month == data.month,
                    Payroll.year == data.year,
                )
            )
        )
        existing_payroll = existing.scalar_one_or_none()
        if existing_payroll:
            results.append(await _enrich_payroll(existing_payroll, db))
            continue

        # Calculate LOP from HR policy
        lop_info = await _calc_lop(emp.id, data.month, data.year, emp.basic_salary, db)

        # Total deductions = fixed deductions + LOP amount
        total_deductions = emp.deductions + lop_info["lop_amount"]
        net_pay = emp.basic_salary + emp.hra + emp.allowances - total_deductions

        payroll = Payroll(
            employee_id=emp.id,
            month=data.month,
            year=data.year,
            basic=emp.basic_salary,
            hra=emp.hra,
            allowances=emp.allowances,
            deductions=total_deductions,  # includes LOP
            net_pay=max(0, net_pay),
            status=PayrollStatus.pending,
        )
        db.add(payroll)
        await db.flush()
        results.append(await _enrich_payroll(payroll, db))

    return results


@router.post("/{payroll_id}/disburse", response_model=PayrollOut)
async def disburse_salary(
    payroll_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(Payroll).where(Payroll.id == payroll_id))
    payroll = result.scalar_one_or_none()
    if not payroll:
        raise HTTPException(status_code=404, detail="Payroll record not found")
    if payroll.status == PayrollStatus.paid:
        raise HTTPException(status_code=400, detail="Salary already disbursed")

    emp_result = await db.execute(select(Employee).where(Employee.id == payroll.employee_id))
    emp = emp_result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    payment_type = "UPI" if emp.upi_id else "IMPS"
    axis_resp = await axis_bank.initiate_payment(
        payment_type=payment_type,
        beneficiary_name=emp.name,
        amount=payroll.net_pay,
        beneficiary_account=emp.bank_account,
        beneficiary_ifsc=emp.ifsc_code,
        upi_id=emp.upi_id,
        remarks=f"Salary {payroll.month}/{payroll.year} - {emp.name}",
    )

    txn = Transaction(
        reference=axis_resp["reference"],
        payment_type=payment_type,
        beneficiary_name=emp.name,
        beneficiary_account=emp.bank_account,
        beneficiary_ifsc=emp.ifsc_code,
        upi_id=emp.upi_id,
        amount=payroll.net_pay,
        status=TransactionStatus.success if axis_resp["success"] else TransactionStatus.failed,
        remarks=f"Salary {payroll.month}/{payroll.year}",
        axis_response=str(axis_resp),
    )
    db.add(txn)
    await db.flush()

    if axis_resp["success"]:
        payroll.status = PayrollStatus.paid
        payroll.transaction_ref = axis_resp["reference"]
        payroll.paid_at = datetime.utcnow()
    else:
        payroll.status = PayrollStatus.failed

    await db.flush()
    return await _enrich_payroll(payroll, db)


@router.post("/bulk-disburse")
async def bulk_disburse(
    data: RunPayrollRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    query = select(Payroll).where(
        and_(
            Payroll.month == data.month,
            Payroll.year == data.year,
            Payroll.status == PayrollStatus.pending,
        )
    )
    if data.employee_ids:
        query = query.where(Payroll.employee_id.in_(data.employee_ids))

    result = await db.execute(query)
    payrolls = result.scalars().all()

    processed = 0
    failed = 0
    for payroll in payrolls:
        emp_result = await db.execute(select(Employee).where(Employee.id == payroll.employee_id))
        emp = emp_result.scalar_one_or_none()
        if not emp:
            continue
        payment_type = "UPI" if emp.upi_id else "IMPS"
        axis_resp = await axis_bank.initiate_payment(
            payment_type=payment_type,
            beneficiary_name=emp.name,
            amount=payroll.net_pay,
            beneficiary_account=emp.bank_account,
            beneficiary_ifsc=emp.ifsc_code,
            upi_id=emp.upi_id,
            remarks=f"Salary {payroll.month}/{payroll.year}",
        )
        txn = Transaction(
            reference=axis_resp["reference"],
            payment_type=payment_type,
            beneficiary_name=emp.name,
            amount=payroll.net_pay,
            status=TransactionStatus.success if axis_resp["success"] else TransactionStatus.failed,
            remarks=f"Bulk Salary {payroll.month}/{payroll.year}",
            axis_response=str(axis_resp),
        )
        db.add(txn)
        await db.flush()
        if axis_resp["success"]:
            payroll.status = PayrollStatus.paid
            payroll.transaction_ref = axis_resp["reference"]
            payroll.paid_at = datetime.utcnow()
            processed += 1
        else:
            failed += 1
    return {"processed": processed, "failed": failed, "total": len(payrolls)}
