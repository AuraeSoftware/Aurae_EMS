from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List, Optional
from datetime import date, datetime, time
import math
from app.database import get_db
from app.models.models import Attendance, Employee, AttendanceStatus, User
from app.schemas.schemas import AttendanceOut
from app.middleware.auth import get_current_user, require_manager_or_admin

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

# ── HR POLICY ─────────────────────────────────────────────────────────────────
WORK_START   = time(9, 30)   # 9:30 AM
WORK_END     = time(18, 30)  # 6:30 PM
SAT_END      = time(13, 30)  # 1:30 PM (half day Saturday)
LATE_GRACE   = time(9, 31)   # 9:31 onward = late; clock-in up to 9:30:59 counts as on-time
HALF_DAY_THRESHOLD = time(13, 30)  # clock-in after 1:30 PM = half day
PERMISSION_1H_END = time(10, 30)   # permission 1h: clock-in 9:30–10:30 → approved leave required
PERMISSION_2H_END = time(11, 30)   # permission 2h: clock-in 10:30–11:30 → approved leave required
LATE_LOP_THRESHOLD = 4       # 4 late days → 0.5 day LOP
CL_PER_MONTH = 1             # 1 casual leave per month free
OFFICE_LAT   = 10.3546437
OFFICE_LNG   = 77.9814846
OFFICE_RADIUS_M = 200  # buffer for WiFi/network-based browser location accuracy (typically 50-200m)


def calc_hours(clock_in: str, clock_out: Optional[str]) -> Optional[str]:
    if not clock_out:
        return None
    try:
        fmt = "%H:%M:%S"
        t1 = datetime.strptime(clock_in, fmt)
        t2 = datetime.strptime(clock_out, fmt)
        delta = t2 - t1
        total_sec = int(delta.total_seconds())
        if total_sec < 0:
            return None
        h = total_sec // 3600
        m = (total_sec % 3600) // 60
        return f"{h}h {m:02d}m"
    except Exception:
        return None


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance in metres between two lat/lng points."""
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_saturday() -> bool:
    return datetime.now().weekday() == 5  # 5 = Saturday


def is_sunday() -> bool:
    return datetime.now().weekday() == 6


def nth_weekday_of_month(d: date) -> int:
    """Returns 1 for the 1st occurrence of that weekday in the month, 2 for the 2nd, etc."""
    return (d.day - 1) // 7 + 1


def is_off_saturday(d: Optional[date] = None) -> bool:
    """2nd and 4th Saturdays of the month are full days off (no work, no half-day)."""
    d = d or date.today()
    if d.weekday() != 5:
        return False
    return nth_weekday_of_month(d) in (2, 4)


def is_day_off(d: Optional[date] = None) -> bool:
    """Sunday, or a 2nd/4th Saturday."""
    d = d or date.today()
    return d.weekday() == 6 or is_off_saturday(d)


def get_expected_end() -> time:
    return SAT_END if is_saturday() else WORK_END


async def _enrich(att: Attendance, db: AsyncSession) -> AttendanceOut:
    emp_result = await db.execute(select(Employee).where(Employee.id == att.employee_id))
    emp = emp_result.scalar_one_or_none()
    out = AttendanceOut.model_validate(att)
    if emp:
        out.employee_name = emp.name
        out.employee_role = emp.role
    return out


@router.patch("/{att_id}", response_model=AttendanceOut)
async def correct_attendance(
    att_id: int,
    clock_in: Optional[str] = Body(default=None, embed=True),
    clock_out: Optional[str] = Body(default=None, embed=True),
    clear_clock_out: bool = Body(default=False, embed=True),
    status: Optional[AttendanceStatus] = Body(default=None, embed=True),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    """Manager/Admin correction tool — e.g. to undo a wrong auto-clock-out."""
    result = await db.execute(select(Attendance).where(Attendance.id == att_id))
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    if clear_clock_out:
        att.clock_out = None
        att.hours_worked = None
    elif clock_out is not None:
        att.clock_out = clock_out

    if clock_in is not None:
        att.clock_in = clock_in

    if att.clock_in and att.clock_out:
        att.hours_worked = calc_hours(att.clock_in, att.clock_out)

    if status is not None:
        att.status = status

    await db.flush()
    return await _enrich(att, db)


@router.get("", response_model=List[AttendanceOut])
async def list_attendance(
    date_filter: Optional[date] = Query(default=None),
    employee_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    from app.models.models import UserRole
    query = select(Attendance)
    conditions = []
    if date_filter:
        conditions.append(Attendance.date == date_filter)
    if current.role == UserRole.employee:
        emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
        emp = emp_result.scalar_one_or_none()
        if emp:
            conditions.append(Attendance.employee_id == emp.id)
        else:
            return []
    elif employee_id:
        conditions.append(Attendance.employee_id == employee_id)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(Attendance.date.desc())
    result = await db.execute(query)
    records = result.scalars().all()
    enriched = [await _enrich(r, db) for r in records]

    # For admin/manager viewing a specific past/today date, synthesize "absent" rows
    # for active employees who have no attendance record for that date
    if current.role != UserRole.employee and date_filter:
        existing_emp_ids = {r.employee_id for r in records}
        emp_result = await db.execute(select(Employee).where(Employee.is_active == True))
        all_employees = emp_result.scalars().all()
        check_date_passed = date_filter <= date.today()  # treat any date up to today as past
        is_off_day_for_date = is_day_off(date_filter)
        if check_date_passed and not is_off_day_for_date:
            for emp in all_employees:
                if emp.id not in existing_emp_ids:
                    enriched.append(AttendanceOut(
                        id=-(abs(hash(emp.id + str(date_filter))) % 1000000),
                        employee_id=emp.id,
                        employee_name=emp.name,
                        employee_role=emp.role,
                        date=date_filter,
                        clock_in=None,
                        clock_out=None,
                        hours_worked=None,
                        status=AttendanceStatus.absent,
                    ))
    return enriched


@router.post("/clock-in", response_model=AttendanceOut)
async def clock_in(
    client_time: Optional[str] = Body(default=None, embed=True),
    latitude: Optional[float] = Body(default=None, embed=True),
    longitude: Optional[float] = Body(default=None, embed=True),
    accuracy: Optional[float] = Body(default=None, embed=True),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    import re as _re
    if is_sunday():
        raise HTTPException(status_code=400, detail="Sunday is a day off — no attendance required")
    if is_off_saturday():
        raise HTTPException(status_code=400, detail="2nd/4th Saturday is a day off — no attendance required")

    emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
    emp = emp_result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=400, detail="No employee profile linked to this account")

    today = date.today()
    now = datetime.now()
    # Use client local time if provided and valid (device timezone)
    if client_time and _re.match(r"^\d{2}:\d{2}:\d{2}$", client_time):
        now_time = client_time
        h, m, s = map(int, client_time.split(":"))
        clock_time = time(h, m, s)
    else:
        now_time = now.strftime("%H:%M:%S")
        clock_time = now.time()

    existing = await db.execute(
        select(Attendance).where(and_(Attendance.employee_id == emp.id, Attendance.date == today))
    )
    att = existing.scalar_one_or_none()
    if att and att.clock_in:
        raise HTTPException(status_code=400, detail="Already clocked in today")

    # ── GEOFENCE ENFORCEMENT ────────────────────────────────────────────────
    # WFH days (pre-flagged by a manager via /attendance/wfh) skip the geofence.
    # Everyone else must be physically within OFFICE_RADIUS_M to clock in.
    is_wfh_today = bool(att and att.is_wfh)
    if not is_wfh_today:
        if latitude is None or longitude is None:
            raise HTTPException(
                status_code=400,
                detail="Location access is required to clock in. Please enable location services and try again.",
            )
        distance = haversine_m(latitude, longitude, OFFICE_LAT, OFFICE_LNG)
        if distance > OFFICE_RADIUS_M:
            acc_note = f" (device location accuracy: ~{int(accuracy)}m)" if accuracy else ""
            raise HTTPException(
                status_code=400,
                detail=f"You must be within office premises to clock in — you appear to be ~{int(distance)}m away{acc_note}.",
            )

    # Status logic:
    # 9:30–10:30  → late (but if Permission-1h approved leave exists for today → permission)
    # 10:30–11:30 → late (Permission-2h zone)
    # After 1:30 PM → half_day
    # Exactly on time → present
    if clock_time > HALF_DAY_THRESHOLD:
        st = AttendanceStatus.half_day
    elif clock_time >= LATE_GRACE:
        # Check if employee has an approved Permission leave for today
        from app.models.models import Leave, LeaveStatus
        perm_check = await db.execute(
            select(Leave).where(
                and_(
                    Leave.employee_id == emp.id,
                    Leave.leave_type == "Permission",
                    Leave.from_date == today,
                    Leave.status == LeaveStatus.approved,
                )
            )
        )
        perm_leave = perm_check.scalar_one_or_none()
        if perm_leave:
            st = AttendanceStatus.permission
        else:
            st = AttendanceStatus.late
    else:
        st = AttendanceStatus.present

    if att:
        att.clock_in = now_time
        att.status = st
    else:
        att = Attendance(
            employee_id=emp.id,
            date=today,
            clock_in=now_time,
            status=st,
        )
        db.add(att)
    await db.flush()
    return await _enrich(att, db)


@router.post("/clock-out", response_model=AttendanceOut)
async def clock_out(
    client_time: Optional[str] = Body(default=None, embed=True),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    import re as _re
    emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
    emp = emp_result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=400, detail="No employee profile linked")

    today = date.today()
    # Use client local time if provided
    if client_time and _re.match(r"^\d{2}:\d{2}:\d{2}$", client_time):
        now_time = client_time
    else:
        now_time = datetime.now().strftime("%H:%M:%S")

    result = await db.execute(
        select(Attendance).where(and_(Attendance.employee_id == emp.id, Attendance.date == today))
    )
    att = result.scalar_one_or_none()
    if not att or not att.clock_in:
        raise HTTPException(status_code=400, detail="Not clocked in today")
    if att.clock_out:
        raise HTTPException(status_code=400, detail="Already clocked out today")

    att.clock_out = now_time
    att.hours_worked = calc_hours(att.clock_in, now_time)
    att.clock_out_source = "manual"
    await db.flush()
    return await _enrich(att, db)


@router.post("/auto-clock-out", response_model=AttendanceOut)
async def auto_clock_out(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Called by the client-side shift-end watcher once the sharp 6:30 PM /
    1:30 PM Saturday cutoff has passed (IST, per the browser's clock).

    IMPORTANT: this always records the CUTOFF time itself, never server wall-clock
    time. Using `datetime.now()` here previously caused clock-outs to be stamped
    with the server container's OS time — which on Railway (and most cloud hosts)
    defaults to UTC, not IST. UTC is 5 hours 30 minutes behind IST, so a genuine
    6:30 PM IST shift-end was being recorded as 1:00 PM — exactly matching the
    reported bug. Storing the fixed cutoff constant sidesteps server timezone
    entirely, matching the same safe approach already used by the scheduled job
    below.
    """
    emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
    emp = emp_result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=400, detail="No employee profile linked")

    today = date.today()
    is_sat = today.weekday() == 5
    cutoff_str = (SAT_END if is_sat else WORK_END).strftime("%H:%M:%S")

    result = await db.execute(
        select(Attendance).where(and_(Attendance.employee_id == emp.id, Attendance.date == today))
    )
    att = result.scalar_one_or_none()
    if not att or not att.clock_in:
        raise HTTPException(status_code=400, detail="Not clocked in today")
    if att.clock_out:
        return await _enrich(att, db)  # already clocked out

    att.clock_out = cutoff_str
    att.hours_worked = calc_hours(att.clock_in, cutoff_str)
    att.clock_out_source = "auto_shift_end"
    await db.flush()
    return await _enrich(att, db)


async def run_scheduled_auto_clockout():
    """Called by the APScheduler job in main.py at 18:30 (Mon-Fri) and 13:30 (Sat) IST.
    Clocks out anyone still clocked-in for today so hours_worked gets recorded even
    if their browser tab was closed before the shift-end watcher could fire."""
    from app.database import AsyncSessionLocal
    print(f"[auto-clockout] scheduled job fired at server time {datetime.now().isoformat()}")
    async with AsyncSessionLocal() as db:
        today = date.today()
        if is_day_off(today):  # Sunday, or 2nd/4th Saturday — nothing to do
            print(f"[auto-clockout] {today} is a day off, skipping")
            return
        cutoff = SAT_END if today.weekday() == 5 else WORK_END
        result = await db.execute(
            select(Attendance).where(
                and_(Attendance.date == today, Attendance.clock_in.isnot(None), Attendance.clock_out.is_(None))
            )
        )
        records = result.scalars().all()
        cutoff_str = cutoff.strftime("%H:%M:%S")
        for att in records:
            att.clock_out = cutoff_str
            att.hours_worked = calc_hours(att.clock_in, cutoff_str)
            att.clock_out_source = "auto_shift_end"
        if records:
            print(f"[auto-clockout] clocked out {len(records)} employee(s) at {cutoff_str}")
            await db.commit()


@router.get("/today-stats")
async def today_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_manager_or_admin),
):
    today = date.today()
    result = await db.execute(select(Attendance).where(Attendance.date == today))
    records = result.scalars().all()
    clocked_in_ids = {r.employee_id for r in records if r.clock_in}

    # Count active employees who have NOT clocked in and are not on leave as absent
    emp_result = await db.execute(select(Employee).where(Employee.is_active == True))
    all_employees = emp_result.scalars().all()
    on_leave_ids = {r.employee_id for r in records if r.status == AttendanceStatus.leave}
    not_clocked_in = [e for e in all_employees if e.id not in clocked_in_ids and e.id not in on_leave_ids]

    # Only count as absent if work hours have started (after 9:30 AM) — avoid false absent early morning
    now_t = datetime.now().time()
    computed_absent = len(not_clocked_in) if (now_t > WORK_START and not is_sunday() and not is_off_saturday()) else 0

    return {
        "present": sum(1 for r in records if r.status == AttendanceStatus.present),
        "late": sum(1 for r in records if r.status == AttendanceStatus.late),
        "half_day": sum(1 for r in records if r.status == AttendanceStatus.half_day),
        "leave": sum(1 for r in records if r.status == AttendanceStatus.leave),
        "absent": sum(1 for r in records if r.status == AttendanceStatus.absent) + computed_absent,
        "total": len(all_employees),
    }


@router.get("/my-status")
async def my_today_status(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
    emp = emp_result.scalar_one_or_none()
    if not emp:
        return {"clocked_in": False, "clocked_out": False, "clock_in": None, "clock_out": None}

    today = date.today()
    result = await db.execute(
        select(Attendance).where(and_(Attendance.employee_id == emp.id, Attendance.date == today))
    )
    att = result.scalar_one_or_none()

    # Work end time depends on day
    work_end = get_expected_end()
    is_sat = is_saturday()
    is_sun = is_sunday()
    is_sat_off = is_off_saturday(today)

    return {
        "clocked_in": bool(att and att.clock_in),
        "clocked_out": bool(att and att.clock_out),
        "clock_in": att.clock_in if att else None,
        "clock_out": att.clock_out if att else None,
        "is_wfh": bool(att and att.is_wfh),
        "hours_worked": att.hours_worked if att else None,
        "status": att.status.value if att else "absent",
        "is_saturday": is_sat,
        "is_sunday": is_sun,
        "is_off_saturday": is_sat_off,
        "work_end": work_end.strftime("%H:%M"),
        "expected_end": "1:30 PM" if is_sat else "6:30 PM",
    }




@router.post("/wfh", status_code=200)
async def mark_wfh(
    employee_id: str = Body(..., embed=True),
    wfh_date: date = Body(..., embed=True),
    wfh_note: Optional[str] = Body(default=None, embed=True),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    """Manager marks an employee as WFH for a given date.
    WFH is only a location flag — employee still MUST clock in to be marked Present.
    If they do not clock in, they remain Absent regardless of WFH marking."""
    # Check if attendance record exists for that day
    result = await db.execute(
        select(Attendance).where(
            and_(Attendance.employee_id == employee_id, Attendance.date == wfh_date)
        )
    )
    att = result.scalar_one_or_none()
    if att:
        # Employee already clocked in — just mark is_wfh on existing record
        att.is_wfh = True
        att.wfh_note = wfh_note
        await db.flush()
        return {"message": "WFH flag added to existing attendance record", "status": att.status.value}
    else:
        # No clock-in yet — create a placeholder WFH record (employee will clock in later)
        emp_result = await db.execute(select(Employee).where(Employee.id == employee_id))
        emp = emp_result.scalar_one_or_none()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        # Create a record with wfh flag but absent status until they actually clock in
        new_att = Attendance(
            employee_id=employee_id,
            date=wfh_date,
            is_wfh=True,
            wfh_note=wfh_note,
            status=AttendanceStatus.absent,  # absent until they clock in
        )
        db.add(new_att)
        await db.flush()
        return {"message": "WFH marked — employee must still clock in to be marked Present", "status": "absent"}



@router.get("/report")
async def attendance_report(
    period: str = Query(default="month", description="week | month | year | custom"),
    year: int = Query(default=None),
    month: Optional[int] = Query(default=None),
    week: Optional[int] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    employee_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    """Generate attendance report for manager — filterable by period and employee."""
    from datetime import timedelta
    import calendar

    today = date.today()
    yr = year or today.year

    if period == "week":
        # Current or specified week (Mon-Sun)
        wk = week or today.isocalendar()[1]
        # Find Monday of that week
        jan4 = date(yr, 1, 4)
        week_start = jan4 + timedelta(weeks=wk - 1) - timedelta(days=jan4.weekday())
        week_end = week_start + timedelta(days=6)
        d_from, d_to = week_start, min(week_end, today)
    elif period == "month":
        mo = month or today.month
        d_from = date(yr, mo, 1)
        last_day = calendar.monthrange(yr, mo)[1]
        d_to = min(date(yr, mo, last_day), today)
    elif period == "year":
        d_from = date(yr, 1, 1)
        d_to = min(date(yr, 12, 31), today)
    elif period == "custom" and date_from and date_to:
        d_from, d_to = date_from, date_to
    else:
        mo = today.month
        d_from = date(yr, mo, 1)
        d_to = today

    # Fetch all active employees (or specific one)
    if employee_id:
        emp_res = await db.execute(select(Employee).where(Employee.id == employee_id, Employee.is_active == True))
    else:
        emp_res = await db.execute(select(Employee).where(Employee.is_active == True))
    employees = emp_res.scalars().all()

    # Fetch attendance in range
    att_conditions = [Attendance.date >= d_from, Attendance.date <= d_to]
    if employee_id:
        att_conditions.append(Attendance.employee_id == employee_id)
    att_res = await db.execute(select(Attendance).where(and_(*att_conditions)))
    records = att_res.scalars().all()

    # Build per-employee summary
    from collections import defaultdict
    emp_records = defaultdict(list)
    for r in records:
        emp_records[r.employee_id].append(r)

    report_rows = []
    for emp in employees:
        recs = emp_records.get(emp.id, [])
        present = sum(1 for r in recs if r.status in (AttendanceStatus.present, AttendanceStatus.late, AttendanceStatus.half_day, AttendanceStatus.wfh))
        late = sum(1 for r in recs if r.status == AttendanceStatus.late)
        half_day = sum(1 for r in recs if r.status == AttendanceStatus.half_day)
        on_leave = sum(1 for r in recs if r.status == AttendanceStatus.leave)
        wfh_days = sum(1 for r in recs if r.is_wfh)

        # Count working days (Mon-Sat, excluding Sun) in range
        total_working = sum(1 for n in range((d_to - d_from).days + 1) if not is_day_off(d_from + timedelta(days=n)))
        absent = max(0, total_working - present - on_leave)
        late_lop = (late // LATE_LOP_THRESHOLD) * 0.5
        half_lop = half_day * 0.5
        # Absent + On Leave combined: 1 day is allowed free: anything beyond that is LOP
        absent_leave_lop = max(0, (absent + on_leave) - 1)

        report_rows.append({
            "employee_id": emp.id,
            "employee_name": emp.name,
            "employee_role": emp.role,
            "period_from": str(d_from),
            "period_to": str(d_to),
            "total_working_days": total_working,
            "present": present,
            "late": late,
            "half_day": half_day,
            "on_leave": on_leave,
            "wfh_days": wfh_days,
            "absent": absent,
            "late_lop": late_lop,
            "half_day_lop": half_lop,
            "absent_leave_lop": absent_leave_lop,
            "total_lop": late_lop + half_lop + absent_leave_lop,
        })

    return {
        "period": period,
        "from": str(d_from),
        "to": str(d_to),
        "generated_at": str(today),
        "rows": report_rows,
    }

@router.get("/monthly-summary/{employee_id}")
async def monthly_summary(
    employee_id: str,
    month: int = Query(...),
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    from app.models.models import UserRole
    if current.role == UserRole.employee:
        emp_check = await db.execute(select(Employee).where(Employee.user_id == current.id))
        own_emp = emp_check.scalar_one_or_none()
        if not own_emp or own_emp.id != employee_id:
            raise HTTPException(status_code=403, detail="You can only view your own attendance summary")
    """Returns attendance summary with CL, late count, and LOP for payroll."""
    from app.models.models import Leave, LeaveStatus, LeaveType
    import calendar

    result = await db.execute(
        select(Attendance).where(
            and_(
                Attendance.employee_id == employee_id,
                func.extract("month", Attendance.date) == month,
                func.extract("year", Attendance.date) == year,
            )
        )
    )
    records = result.scalars().all()

    late_count = sum(1 for r in records if r.status == AttendanceStatus.late)
    half_day_count = sum(1 for r in records if r.status == AttendanceStatus.half_day)
    on_leave_count = sum(1 for r in records if r.status == AttendanceStatus.leave)
    present_count = sum(1 for r in records if r.status in (AttendanceStatus.present, AttendanceStatus.late, AttendanceStatus.half_day, AttendanceStatus.wfh))

    # CL taken this month — kept for display only ("CL's Taken" on the payslip);
    # the LOP calculation below uses the combined Absent+OnLeave rule instead,
    # which already covers every approved leave type, not just Casual Leave.
    leave_result = await db.execute(
        select(Leave).where(
            and_(
                Leave.employee_id == employee_id,
                Leave.leave_type == LeaveType.casual,
                Leave.status == LeaveStatus.approved,
                func.extract("month", Leave.from_date) == month,
                func.extract("year", Leave.from_date) == year,
            )
        )
    )
    leaves = leave_result.scalars().all()
    cl_taken = sum((l.to_date - l.from_date).days + 1 for l in leaves)

    # Working days in month (Mon-Sat, excluding Sundays / 2nd & 4th Saturdays)
    _, days_in_month = calendar.monthrange(year, month)
    working_days = sum(1 for day in range(1, days_in_month + 1) if not is_day_off(date(year, month, day)))

    absent_count = max(0, working_days - present_count - on_leave_count)

    # LOP from 4+ late clock-ins (every 4 lates = 0.5 day)
    late_lop_days = (late_count // LATE_LOP_THRESHOLD) * 0.5

    # LOP from half-day clock-ins (clock-in after 1:30 PM = 0.5 day each)
    half_day_lop_days = half_day_count * 0.5

    # Absent + On Leave (any approved type) combined: 1 day/month is free
    absent_leave_lop_days = max(0, (absent_count + on_leave_count) - 1)

    total_lop = late_lop_days + half_day_lop_days + absent_leave_lop_days

    return {
        "employee_id": employee_id,
        "month": month,
        "year": year,
        "present_days": present_count,
        "late_count": late_count,
        "half_day_count": half_day_count,
        "absent_count": absent_count,
        "on_leave_count": on_leave_count,
        "cl_taken": cl_taken,
        "cl_free": CL_PER_MONTH,
        "late_lop_days": late_lop_days,
        "half_day_lop_days": half_day_lop_days,
        "absent_leave_lop_days": absent_leave_lop_days,
        "total_lop_days": total_lop,
    }
