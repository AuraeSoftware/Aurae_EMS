from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Optional
import uuid
from datetime import date
from app.database import get_db
from app.models.models import Leave, Employee, LeaveStatus, AttendanceStatus, Attendance, User
from app.schemas.schemas import LeaveCreate, LeaveAction, LeaveOut
from app.middleware.auth import get_current_user, require_manager_or_admin

router = APIRouter(prefix="/api/leaves", tags=["leaves"])


async def _enrich_leave(lv: Leave, db: AsyncSession) -> LeaveOut:
    emp_result = await db.execute(select(Employee).where(Employee.id == lv.employee_id))
    emp = emp_result.scalar_one_or_none()
    out = LeaveOut.model_validate(lv)
    if emp:
        out.employee_name = emp.name
    return out


@router.get("", response_model=List[LeaveOut])
async def list_leaves(
    status: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    from app.models.models import UserRole
    query = select(Leave)
    if current.role == UserRole.employee:
        emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
        emp = emp_result.scalar_one_or_none()
        if emp:
            query = query.where(Leave.employee_id == emp.id)
        else:
            return []
    if status:
        query = query.where(Leave.status == status)
    query = query.order_by(Leave.created_at.desc())
    result = await db.execute(query)
    return [await _enrich_leave(lv, db) for lv in result.scalars().all()]


@router.post("", response_model=LeaveOut, status_code=201)
async def request_leave(
    data: LeaveCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
    emp = emp_result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=400, detail="No employee profile linked")

    days = (data.to_date - data.from_date).days + 1
    # Permission leaves are always 1 day with minimal days count
    actual_days = days if data.leave_type != "Permission" else 0  # permission doesn't deduct days
    leave = Leave(
        id="L" + uuid.uuid4().hex[:7].upper(),
        employee_id=emp.id,
        leave_type=data.leave_type,
        from_date=data.from_date,
        to_date=data.to_date,
        days=actual_days,
        reason=data.reason,
        permission_hours=data.permission_hours if data.leave_type == "Permission" else None,
        status=LeaveStatus.pending,
    )
    db.add(leave)
    await db.flush()
    return await _enrich_leave(leave, db)


@router.patch("/{leave_id}/action", response_model=LeaveOut)
async def action_leave(
    leave_id: str,
    data: LeaveAction,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_manager_or_admin),
):
    result = await db.execute(select(Leave).where(Leave.id == leave_id))
    leave = result.scalar_one_or_none()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")

    if data.action == "approved":
        leave.status = LeaveStatus.approved
        leave.approved_by = current.id
        # Mark attendance as leave for those days
        d = leave.from_date
        while d <= leave.to_date:
            existing = await db.execute(
                select(Attendance).where(
                    and_(Attendance.employee_id == leave.employee_id, Attendance.date == d)
                )
            )
            att = existing.scalar_one_or_none()
            if not att:
                att = Attendance(employee_id=leave.employee_id, date=d, status=AttendanceStatus.leave)
                db.add(att)
            else:
                att.status = AttendanceStatus.leave
            from datetime import timedelta
            d += timedelta(days=1)
    elif data.action == "rejected":
        leave.status = LeaveStatus.rejected
        leave.approved_by = current.id
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    await db.flush()
    return await _enrich_leave(leave, db)


@router.delete("/{leave_id}", status_code=200)
async def delete_leave(
    leave_id: str,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Manager/Admin can delete any leave. Employee can delete their own pending leave."""
    from app.models.models import UserRole
    result = await db.execute(select(Leave).where(Leave.id == leave_id))
    leave = result.scalar_one_or_none()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")

    if current.role == UserRole.employee:
        emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
        emp = emp_result.scalar_one_or_none()
        if not emp or emp.id != leave.employee_id:
            raise HTTPException(status_code=403, detail="Cannot delete another employee's leave")
        if leave.status != LeaveStatus.pending:
            raise HTTPException(status_code=400, detail="Can only delete pending leaves")

    await db.delete(leave)
    await db.flush()
    return {"message": "Leave deleted", "id": leave_id}
