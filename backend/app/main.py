from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.database import engine, Base, AsyncSessionLocal, get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.routers import auth, users, employees, attendance, leaves, clients, projects, payroll, invoices, payments, dashboard, chat, receipts
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent patch for deployments created before kanban_stage existed
        # (create_all only creates missing tables, it never alters existing ones)
        await conn.execute(text(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS kanban_stage taskstatus DEFAULT 'todo'"
        ))
        # Idempotent patch for the OS2 Studio Tracker.xlsx-format project fields.
        # NOTE: tracker_status is a plain VARCHAR, not a native Postgres enum — SQLAlchemy's
        # Enum() type defaults to using the Python enum member NAME (e.g. "inprogress") for
        # native enum labels, not its VALUE ("Inprogress"), which silently produced a type
        # that rejected the very values the app writes. Plain string sidesteps that entirely.
        await conn.execute(text("DROP TYPE IF EXISTS trackerstatus"))
        await conn.execute(text(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS tracker_status VARCHAR(20) DEFAULT 'Inprogress'"
        ))
        for col_sql in [
            "asset_type VARCHAR(100)",
            "region VARCHAR(100)",
            "asset_file_name VARCHAR(300)",
            "expected_date DATE",
            "completion_date_design DATE",
            "project_lead VARCHAR(120)",
            "asset_content_url VARCHAR(500)",
            "sample_documents VARCHAR(500)",
            "feedback_revision TEXT",
            "design_url VARCHAR(500)",
        ]:
            await conn.execute(text(f"ALTER TABLE projects ADD COLUMN IF NOT EXISTS {col_sql}"))
        # Widen design_url (originally VARCHAR(500)) to TEXT so it can comfortably
        # hold multiple comma-separated URLs without truncation risk.
        await conn.execute(text("ALTER TABLE projects ALTER COLUMN design_url TYPE TEXT"))
        await conn.execute(text(
            "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS amount_received FLOAT DEFAULT 0"
        ))
        await conn.execute(text(
            "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS clock_out_source VARCHAR(20)"
        ))
        # Backfill: invoices already marked Paid before per-payment tracking existed
        # had amount_received stuck at 0 — bring the data in line with their status.
        await conn.execute(text(
            "UPDATE invoices SET amount_received = total_amount WHERE status = 'paid' AND amount_received < total_amount"
        ))
    # Seed initial data if requested
    if settings.SEED_DB:
        await seed_initial_data()

    # Server-side auto clock-out: fires even if no employee has the app open.
    # 6:30 PM sharp Mon-Fri, 1:30 PM sharp Saturday.
    scheduler.add_job(attendance.run_scheduled_auto_clockout, CronTrigger(day_of_week="mon-fri", hour=18, minute=30))
    scheduler.add_job(attendance.run_scheduled_auto_clockout, CronTrigger(day_of_week="sat", hour=13, minute=30))
    scheduler.start()

    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Os² Studio EMS API",
    description="Enterprise Management System — Os² Studio",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Register routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(employees.router)
app.include_router(attendance.router)
app.include_router(leaves.router)
app.include_router(clients.router)
app.include_router(projects.router)
app.include_router(payroll.router)
app.include_router(invoices.router)
app.include_router(payments.router)
app.include_router(dashboard.router)
app.include_router(chat.router)
app.include_router(receipts.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "app": "Os² Studio EMS"}


@app.post("/api/admin/reset-passwords")
async def reset_passwords(db: AsyncSession = Depends(get_db)):
    """Emergency password reset for seeded users — used once after broken deployment."""
    import os as _os
    from app.models.models import User
    from sqlalchemy import select
    from app.middleware.auth import hash_password as _hp
    
    password_map = {
        "admin@auraesoftwaresolutions.com": "admin123",
    }
    updated = []
    for email, pwd in password_map.items():
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            user.password_hash = _hp(pwd)
            updated.append(email)
    await db.commit()
    return {"status": "reset", "updated": updated}


# ── Seed Data ─────────────────────────────────────────────────────────────────

async def seed_initial_data():
    from sqlalchemy import select
    from app.models.models import User, Employee, Client, Project, Task, Invoice, Attendance, Leave
    from app.models.models import (
        UserRole, ProjectStatus, TaskPriority, TaskStatus,
        InvoiceStatus, AttendanceStatus, LeaveStatus
    )
    from app.middleware.auth import hash_password
    from datetime import date, timedelta
    import uuid

    async with AsyncSessionLocal() as db:
        # Check if already seeded
        check = await db.execute(select(User).where(User.email == "admin@auraesoftwaresolutions.com"))
        existing_admin = check.scalar_one_or_none()
        if existing_admin:
            # Verify password works — fix if broken from crash-loop deployments
            from app.middleware.auth import verify_password as _vp
            if _vp("admin123", existing_admin.password_hash):
                return  # Already seeded and healthy
            # Passwords broken — reset all seeded users
            password_map = {
                "admin@auraesoftwaresolutions.com": "admin123",
            }
            all_users_r = await db.execute(select(User))
            for u in all_users_r.scalars().all():
                if u.email in password_map:
                    u.password_hash = hash_password(password_map[u.email])
            await db.commit()
            print("✅ Passwords self-healed for seeded users", flush=True)
            return

        # ── Users ──────────────────────────────────────────────────────────────
        users = [
            User(id="U001", name="Admin User", email="admin@auraesoftwaresolutions.com",
                 password_hash=hash_password("admin123"), role=UserRole.admin, avatar_initials="AD"),
        ]
        db.add_all(users)
        await db.flush()

        # No dummy data — all data added via admin panel
        await db.commit()
        print("✅ Database seeded successfully!")
