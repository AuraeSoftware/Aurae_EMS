from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Date, Text,
    ForeignKey, Enum as SAEnum, Table, Column, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


# ── Enums ──────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    employee = "employee"


class AttendanceStatus(str, enum.Enum):
    present = "present"
    late = "late"
    absent = "absent"
    leave = "leave"
    half_day = "half_day"
    wfh = "wfh"
    permission = "permission"


class LeaveType(str, enum.Enum):
    casual = "Casual Leave"
    sick = "Sick Leave"
    permission = "Permission"


class LeaveStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ProjectStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    on_hold = "on_hold"
    cancelled = "cancelled"


class TrackerStatus(str, enum.Enum):
    completed = "Completed"
    inprogress = "Inprogress"
    on_hold = "On Hold"
    in_review = "In Review"


class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TaskStatus(str, enum.Enum):
    todo = "todo"
    inprogress = "inprogress"
    review = "review"
    done = "done"


class PayrollStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"


class InvoiceStatus(str, enum.Enum):
    draft = "draft"
    pending = "pending"
    paid = "paid"
    overdue = "overdue"
    cancelled = "cancelled"


class PaymentType(str, enum.Enum):
    UPI = "UPI"
    NEFT = "NEFT"
    RTGS = "RTGS"
    IMPS = "IMPS"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    success = "success"
    failed = "failed"


class PaymentRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    processed = "processed"


# ── Association Tables ─────────────────────────────────────────────────────────

project_members = Table(
    "project_members",
    Base.metadata,
    Column("project_id", String, ForeignKey("projects.id"), primary_key=True),
    Column("employee_id", String, ForeignKey("employees.id"), primary_key=True),
)


# ── Models ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.employee)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_initials: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    employee: Mapped[Optional["Employee"]] = relationship("Employee", back_populates="user", uselist=False)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("users.id"), nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    role: Mapped[str] = mapped_column(String(100))
    department: Mapped[str] = mapped_column(String(100))
    basic_salary: Mapped[float] = mapped_column(Float, default=0)
    hra: Mapped[float] = mapped_column(Float, default=0)
    allowances: Mapped[float] = mapped_column(Float, default=0)
    deductions: Mapped[float] = mapped_column(Float, default=0)
    bank_account: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    ifsc_code: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    upi_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    join_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="employee")
    attendance: Mapped[list["Attendance"]] = relationship("Attendance", back_populates="employee")
    leaves: Mapped[list["Leave"]] = relationship("Leave", back_populates="employee")
    payrolls: Mapped[list["Payroll"]] = relationship("Payroll", back_populates="employee")
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="assignee")
    projects: Mapped[list["Project"]] = relationship("Project", secondary=project_members, back_populates="team")


class Attendance(Base):
    __tablename__ = "attendance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(String(20), ForeignKey("employees.id"))
    date: Mapped[date] = mapped_column(Date)
    clock_in: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    clock_out: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    hours_worked: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[AttendanceStatus] = mapped_column(SAEnum(AttendanceStatus), default=AttendanceStatus.absent)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_wfh: Mapped[bool] = mapped_column(Boolean, default=False)
    wfh_note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # Audit trail: 'manual' (employee clicked Clock Out) or 'auto_shift_end' (sharp
    # 6:30 PM / 1:30 PM Saturday cutoff, client or server-triggered). Lets anyone
    # verify definitively what actually caused a clock-out, instead of guessing.
    clock_out_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    __table_args__ = (UniqueConstraint("employee_id", "date", name="uq_emp_date"),)

    employee: Mapped["Employee"] = relationship("Employee", back_populates="attendance")


class Leave(Base):
    __tablename__ = "leaves"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(20), ForeignKey("employees.id"))
    leave_type: Mapped[str] = mapped_column(String(50))
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)
    days: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    permission_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1 or 2 for Permission type
    status: Mapped[LeaveStatus] = mapped_column(SAEnum(LeaveStatus), default=LeaveStatus.pending)
    approved_by: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    employee: Mapped["Employee"] = relationship("Employee", back_populates="leaves")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_person: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gstin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    total_revenue: Mapped[float] = mapped_column(Float, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    projects: Mapped[list["Project"]] = relationship("Project", back_populates="client")
    invoices: Mapped[list["Invoice"]] = relationship("Invoice", back_populates="client")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    client_id: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("clients.id"), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    document_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    document_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    value: Mapped[float] = mapped_column(Float, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ProjectStatus] = mapped_column(SAEnum(ProjectStatus), default=ProjectStatus.active)
    kanban_stage: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.todo)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ── Tracker fields (matches OS2 Studio Tracker.xlsx format) ─────────────────
    asset_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    asset_file_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    expected_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    completion_date_design: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    project_lead: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    asset_content_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tracker_status: Mapped[str] = mapped_column(String(20), default="Inprogress")
    sample_documents: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    feedback_revision: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    design_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # supports multiple comma-separated URLs

    client: Mapped[Optional["Client"]] = relationship("Client", back_populates="projects")
    team: Mapped[list["Employee"]] = relationship("Employee", secondary=project_members, back_populates="projects")
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="project")
    invoices: Mapped[list["Invoice"]] = relationship("Invoice", back_populates="project")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("projects.id"), nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("employees.id"), nullable=True)
    priority: Mapped[TaskPriority] = mapped_column(SAEnum(TaskPriority), default=TaskPriority.medium)
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.todo)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="tasks")
    assignee: Mapped[Optional["Employee"]] = relationship("Employee", back_populates="tasks")


class Payroll(Base):
    __tablename__ = "payrolls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(String(20), ForeignKey("employees.id"))
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    basic: Mapped[float] = mapped_column(Float, default=0)
    hra: Mapped[float] = mapped_column(Float, default=0)
    allowances: Mapped[float] = mapped_column(Float, default=0)
    deductions: Mapped[float] = mapped_column(Float, default=0)
    net_pay: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[PayrollStatus] = mapped_column(SAEnum(PayrollStatus), default=PayrollStatus.pending)
    transaction_ref: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("employee_id", "month", "year", name="uq_emp_payroll"),)

    employee: Mapped["Employee"] = relationship("Employee", back_populates="payrolls")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    client_id: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("clients.id"), nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("projects.id"), nullable=True)
    project_desc: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    amount: Mapped[float] = mapped_column(Float, default=0)
    gst_amount: Mapped[float] = mapped_column(Float, default=0)
    total_amount: Mapped[float] = mapped_column(Float, default=0)
    amount_received: Mapped[float] = mapped_column(Float, default=0)
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[InvoiceStatus] = mapped_column(SAEnum(InvoiceStatus), default=InvoiceStatus.pending)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    doc_type: Mapped[str] = mapped_column(String(20), default="Invoice")
    client_name_text: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    client: Mapped[Optional["Client"]] = relationship("Client", back_populates="invoices")
    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="invoices")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    payment_type: Mapped[str] = mapped_column(String(10))
    beneficiary_name: Mapped[str] = mapped_column(String(200))
    beneficiary_account: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    beneficiary_ifsc: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    upi_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[TransactionStatus] = mapped_column(SAEnum(TransactionStatus), default=TransactionStatus.pending)
    remarks: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    axis_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    payment_request: Mapped[Optional["PaymentRequest"]] = relationship(
        "PaymentRequest", back_populates="transaction", uselist=False
    )


class PaymentRequest(Base):
    __tablename__ = "payment_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raised_by: Mapped[str] = mapped_column(String(20), ForeignKey("users.id"))
    beneficiary_name: Mapped[str] = mapped_column(String(200))
    beneficiary_account: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    beneficiary_ifsc: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    upi_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payment_type: Mapped[str] = mapped_column(String(10))
    amount: Mapped[float] = mapped_column(Float)
    purpose: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    status: Mapped[PaymentRequestStatus] = mapped_column(
        SAEnum(PaymentRequestStatus), default=PaymentRequestStatus.pending
    )
    approved_by: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("users.id"), nullable=True)
    transaction_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("transactions.id"), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    raiser: Mapped["User"] = relationship("User", foreign_keys=[raised_by])
    approver: Mapped[Optional["User"]] = relationship("User", foreign_keys=[approved_by])
    transaction: Mapped[Optional["Transaction"]] = relationship("Transaction", back_populates="payment_request")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_id: Mapped[str] = mapped_column(String(20), ForeignKey("users.id"))
    sender_name: Mapped[str] = mapped_column(String(120))
    sender_role: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatReadStatus(Base):
    __tablename__ = "chat_read_status"

    user_id: Mapped[str] = mapped_column(String(20), ForeignKey("users.id"), primary_key=True)
    last_read_message_id: Mapped[int] = mapped_column(Integer, default=0)


class Receipt(Base):
    """Tracks OUTGOING payments made BY the office (to vendors, contractors,
    suppliers, etc.) — the mirror image of Invoices, which track money coming IN."""
    __tablename__ = "receipts"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    payee_name: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    amount: Mapped[float] = mapped_column(Float, default=0)
    payment_date: Mapped[date] = mapped_column(Date)
    payment_method: Mapped[str] = mapped_column(String(50), default="Bank Transfer")
    reference_no: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
