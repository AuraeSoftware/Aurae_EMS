from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List, Any
from datetime import datetime, date
from app.models.models import (
    UserRole, AttendanceStatus, LeaveStatus, ProjectStatus,
    TaskPriority, TaskStatus, PayrollStatus, InvoiceStatus,
    TransactionStatus, PaymentRequestStatus, TrackerStatus
)


# ── Auth ───────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserOut"


class RefreshRequest(BaseModel):
    refresh_token: str


# ── User ───────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.employee


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: UserRole
    is_active: bool
    avatar_initials: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Employee ───────────────────────────────────────────────────────────────────

class EmployeeCreate(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    role: str
    department: str
    basic_salary: float = 0
    hra: Optional[float] = None
    allowances: Optional[float] = None
    deductions: Optional[float] = None
    bank_account: Optional[str] = None
    ifsc_code: Optional[str] = None
    upi_id: Optional[str] = None
    join_date: Optional[date] = None
    create_user_account: bool = False
    user_password: Optional[str] = None
    user_role: UserRole = UserRole.employee


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    basic_salary: Optional[float] = None
    hra: Optional[float] = None
    allowances: Optional[float] = None
    deductions: Optional[float] = None
    bank_account: Optional[str] = None
    ifsc_code: Optional[str] = None
    upi_id: Optional[str] = None
    join_date: Optional[date] = None
    is_active: Optional[bool] = None
    user_id: Optional[str] = None


class EmployeeOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    name: str
    email: str
    phone: Optional[str]
    role: str
    department: str
    basic_salary: float
    hra: float
    allowances: float
    deductions: float
    bank_account: Optional[str]
    ifsc_code: Optional[str]
    upi_id: Optional[str]
    join_date: Optional[date]
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Attendance ─────────────────────────────────────────────────────────────────

class ClockInOut(BaseModel):
    employee_id: Optional[str] = None  # admin can clock on behalf


class AttendanceOut(BaseModel):
    id: int
    employee_id: str
    employee_name: Optional[str] = None
    employee_role: Optional[str] = None
    date: date
    clock_in: Optional[str]
    clock_out: Optional[str]
    hours_worked: Optional[str]
    status: AttendanceStatus
    is_wfh: bool = False
    wfh_note: Optional[str] = None
    clock_out_source: Optional[str] = None
    model_config = {"from_attributes": True}


# ── Leave ──────────────────────────────────────────────────────────────────────

class LeaveCreate(BaseModel):
    leave_type: str
    permission_hours: Optional[int] = None  # 1 or 2 for Permission type
    from_date: date
    to_date: date
    reason: Optional[str] = None


class LeaveAction(BaseModel):
    action: str  # "approved" or "rejected"
    reason: Optional[str] = None


class LeaveOut(BaseModel):
    id: str
    employee_id: str
    employee_name: Optional[str] = None
    leave_type: str
    permission_hours: Optional[int] = None
    from_date: date
    to_date: date
    days: int
    reason: Optional[str]
    status: LeaveStatus
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Client ─────────────────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    name: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    industry: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None


class ClientUpdate(ClientCreate):
    name: Optional[str] = None


class ClientOut(BaseModel):
    id: str
    name: str
    contact_person: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    industry: Optional[str]
    total_revenue: float
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Project ────────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    client_id: Optional[str] = None
    description: Optional[str] = None
    document_url: Optional[str] = None
    document_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    value: float = 0
    team_ids: List[str] = []
    # Tracker fields
    asset_type: Optional[str] = None
    region: Optional[str] = None
    asset_file_name: Optional[str] = None
    expected_date: Optional[date] = None
    completion_date_design: Optional[date] = None
    project_lead: Optional[str] = None
    asset_content_url: Optional[str] = None
    tracker_status: Optional[TrackerStatus] = None
    sample_documents: Optional[str] = None
    feedback_revision: Optional[str] = None
    design_url: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    client_id: Optional[str] = None
    description: Optional[str] = None
    document_url: Optional[str] = None
    document_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    value: Optional[float] = None
    progress: Optional[int] = None
    status: Optional[ProjectStatus] = None
    kanban_stage: Optional[TaskStatus] = None
    team_ids: Optional[List[str]] = None
    # Tracker fields
    asset_type: Optional[str] = None
    region: Optional[str] = None
    asset_file_name: Optional[str] = None
    expected_date: Optional[date] = None
    completion_date_design: Optional[date] = None
    project_lead: Optional[str] = None
    asset_content_url: Optional[str] = None
    tracker_status: Optional[TrackerStatus] = None
    sample_documents: Optional[str] = None
    feedback_revision: Optional[str] = None
    design_url: Optional[str] = None


class ProjectOut(BaseModel):
    id: str
    name: str
    client_id: Optional[str]
    client_name: Optional[str] = None
    description: Optional[str]
    document_url: Optional[str] = None
    document_name: Optional[str] = None
    start_date: Optional[date]
    end_date: Optional[date]
    value: float
    progress: int
    status: ProjectStatus
    kanban_stage: TaskStatus = TaskStatus.todo
    team: List[str] = []
    team_names: List[str] = []
    created_at: datetime
    # Tracker fields
    asset_type: Optional[str] = None
    region: Optional[str] = None
    asset_file_name: Optional[str] = None
    expected_date: Optional[date] = None
    completion_date_design: Optional[date] = None
    project_lead: Optional[str] = None
    asset_content_url: Optional[str] = None
    tracker_status: TrackerStatus = TrackerStatus.inprogress
    sample_documents: Optional[str] = None
    feedback_revision: Optional[str] = None
    design_url: Optional[str] = None
    model_config = {"from_attributes": True}


# ── Task ───────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    project_id: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: TaskPriority = TaskPriority.medium
    status: TaskStatus = TaskStatus.todo
    due_date: Optional[date] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    project_id: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    due_date: Optional[date] = None


class TaskOut(BaseModel):
    id: str
    title: str
    description: Optional[str]
    project_id: Optional[str]
    project_name: Optional[str] = None
    assigned_to: Optional[str]
    assignee_name: Optional[str] = None
    priority: TaskPriority
    status: TaskStatus
    due_date: Optional[date]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Payroll ────────────────────────────────────────────────────────────────────

class PayrollOut(BaseModel):
    id: int
    employee_id: str
    employee_name: Optional[str] = None
    employee_role: Optional[str] = None
    month: int
    year: int
    basic: float
    hra: float
    allowances: float
    deductions: float
    net_pay: float
    status: PayrollStatus
    transaction_ref: Optional[str]
    paid_at: Optional[datetime]
    model_config = {"from_attributes": True}


class RunPayrollRequest(BaseModel):
    month: int
    year: int
    employee_ids: Optional[List[str]] = None  # None = all


# ── Invoice ────────────────────────────────────────────────────────────────────

class InvoiceCreate(BaseModel):
    client_id: Optional[str] = None
    project_id: Optional[str] = None
    project_desc: Optional[str] = None
    amount: float
    gst_rate: float = 18.0
    due_days: int = 30
    notes: Optional[str] = None


class InvoiceUpdate(BaseModel):
    status: Optional[InvoiceStatus] = None
    notes: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    amount: Optional[float] = None
    gst_rate: Optional[float] = None
    client_name_text: Optional[str] = None


class InvoiceOut(BaseModel):
    id: str
    client_id: Optional[str]
    client_name: Optional[str] = None
    client_name_text: Optional[str] = None
    project_id: Optional[str]
    project_desc: Optional[str]
    amount: float
    gst_amount: float
    total_amount: float
    amount_received: float = 0
    issue_date: date
    due_date: date
    status: InvoiceStatus
    doc_type: Optional[str] = "Invoice"
    notes: Optional[str] = None
    paid_at: Optional[datetime]
    created_at: datetime
    model_config = {"from_attributes": True}


class InvoicePayment(BaseModel):
    amount: float


# ── Payment ────────────────────────────────────────────────────────────────────

class PaymentRequestCreate(BaseModel):
    beneficiary_name: str
    payment_type: str
    amount: float
    purpose: Optional[str] = None
    beneficiary_account: Optional[str] = None
    beneficiary_ifsc: Optional[str] = None
    upi_id: Optional[str] = None


class PaymentApprovalAction(BaseModel):
    action: str  # "approved" or "rejected"
    reason: Optional[str] = None


class PaymentRequestOut(BaseModel):
    id: int
    raised_by: str
    raiser_name: Optional[str] = None
    beneficiary_name: str
    payment_type: str
    amount: float
    purpose: Optional[str]
    status: PaymentRequestStatus
    approved_by: Optional[str]
    approver_name: Optional[str] = None
    transaction_id: Optional[int]
    rejection_reason: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


class TransactionOut(BaseModel):
    id: int
    reference: str
    payment_type: str
    beneficiary_name: str
    amount: float
    status: TransactionStatus
    remarks: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


class BankBalanceOut(BaseModel):
    account_number: str
    balance: float
    currency: str = "INR"
    last_refreshed: str


# ── Dashboard ──────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    monthly_revenue: float
    active_projects: int
    total_employees: int
    pending_invoices: int
    overdue_invoices: int
    present_today: int
    on_leave_today: int
    pending_leaves: int
    pending_payment_requests: int


# ── Chat ───────────────────────────────────────────────────────────────────────

class ChatMessageOut(BaseModel):
    id: int
    sender_id: str
    sender_name: str
    sender_role: str
    message: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ChatUnreadOut(BaseModel):
    unread_count: int
    last_message_id: int


# ── Receipts (outgoing payments) ────────────────────────────────────────────────

class ReceiptCreate(BaseModel):
    payee_name: str
    purpose: Optional[str] = None
    amount: float
    payment_date: date
    payment_method: str = "Bank Transfer"
    reference_no: Optional[str] = None
    notes: Optional[str] = None


class ReceiptUpdate(BaseModel):
    payee_name: Optional[str] = None
    purpose: Optional[str] = None
    amount: Optional[float] = None
    payment_date: Optional[date] = None
    payment_method: Optional[str] = None
    reference_no: Optional[str] = None
    notes: Optional[str] = None


class ReceiptOut(BaseModel):
    id: str
    payee_name: str
    purpose: Optional[str] = None
    amount: float
    payment_date: date
    payment_method: str
    reference_no: Optional[str] = None
    notes: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}
