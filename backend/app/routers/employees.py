from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import uuid
from app.database import get_db
from app.models.models import Employee, User
from app.schemas.schemas import EmployeeCreate, EmployeeUpdate, EmployeeOut
from app.middleware.auth import require_admin, require_manager_or_admin, get_current_user, hash_password

router = APIRouter(prefix="/api/employees", tags=["employees"])


def gen_emp_id() -> str:
    return "E" + uuid.uuid4().hex[:6].upper()


@router.get("", response_model=List[EmployeeOut])
async def list_employees(
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    result = await db.execute(select(Employee).where(Employee.is_active == True).order_by(Employee.name))
    return [EmployeeOut.model_validate(e) for e in result.scalars().all()]


@router.post("", response_model=EmployeeOut, status_code=201)
async def create_employee(
    data: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    # Check email uniqueness
    existing = await db.execute(select(Employee).where(Employee.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Employee email already exists")

    hra = data.hra if data.hra is not None else round(data.basic_salary * 0.40)
    allowances = data.allowances if data.allowances is not None else round(data.basic_salary * 0.10)
    deductions = data.deductions if data.deductions is not None else round(data.basic_salary * 0.12)

    emp_id = gen_emp_id()
    employee = Employee(
        id=emp_id,
        name=data.name,
        email=data.email,
        phone=data.phone,
        role=data.role,
        department=data.department,
        basic_salary=data.basic_salary,
        hra=hra,
        allowances=allowances,
        deductions=deductions,
        bank_account=data.bank_account,
        ifsc_code=data.ifsc_code,
        upi_id=data.upi_id,
        join_date=data.join_date,
    )

    # Optionally create linked user account
    if data.create_user_account and data.user_password:
        user_check = await db.execute(select(User).where(User.email == data.email))
        if not user_check.scalar_one_or_none():
            user = User(
                id="U" + uuid.uuid4().hex[:7].upper(),
                name=data.name,
                email=data.email,
                password_hash=hash_password(data.user_password),
                role=data.user_role,
                avatar_initials=data.name[:2].upper(),
            )
            db.add(user)
            await db.flush()
            employee.user_id = user.id

    db.add(employee)
    await db.flush()
    return EmployeeOut.model_validate(employee)


@router.get("/me", response_model=EmployeeOut)
async def my_profile(db: AsyncSession = Depends(get_db), current=Depends(get_current_user)):
    result = await db.execute(select(Employee).where(Employee.user_id == current.id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee profile not found for this user")
    return EmployeeOut.model_validate(emp)


@router.get("/{emp_id}", response_model=EmployeeOut)
async def get_employee(emp_id: str, db: AsyncSession = Depends(get_db), current=Depends(get_current_user)):
    result = await db.execute(select(Employee).where(Employee.id == emp_id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return EmployeeOut.model_validate(emp)


@router.patch("/{emp_id}", response_model=EmployeeOut)
async def update_employee(
    emp_id: str,
    data: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(Employee).where(Employee.id == emp_id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(emp, field, value)
    await db.flush()
    return EmployeeOut.model_validate(emp)


@router.delete("/{emp_id}", status_code=204)
async def delete_employee(emp_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(Employee).where(Employee.id == emp_id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp.is_active = False  # Soft delete
    await db.flush()
