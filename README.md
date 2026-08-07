# Aurae Software Solutions — Enterprise Management System v2.0
_(Built by OS2 Studio. See HANDOFF_NOTES.md for what to configure before going live.)_

Full-stack ERP with **FastAPI + PostgreSQL + Docker + Axis Bank Payment Gateway**

---

## 📁 Project Structure

```
os2-studio-ems/
├── backend/
│   ├── app/
│   │   ├── main.py          ← FastAPI app + seed data
│   │   ├── config.py        ← Settings from .env
│   │   ├── database.py      ← Async SQLAlchemy engine
│   │   ├── models/
│   │   │   └── models.py    ← All ORM models (User, Employee, etc.)
│   │   ├── schemas/
│   │   │   └── schemas.py   ← Pydantic request/response schemas
│   │   ├── routers/
│   │   │   ├── auth.py      ← JWT login / refresh / me
│   │   │   ├── users.py     ← User CRUD (Admin only)
│   │   │   ├── employees.py ← Employee CRUD
│   │   │   ├── attendance.py← Clock in/out, reports
│   │   │   ├── leaves.py    ← Leave requests + approvals
│   │   │   ├── clients.py   ← Client CRUD
│   │   │   ├── projects.py  ← Projects + Tasks + Kanban
│   │   │   ├── payroll.py   ← Salary + Axis Bank disbursement
│   │   │   ├── invoices.py  ← Invoice CRUD + overdue check
│   │   │   ├── payments.py  ← Payment requests + Axis Bank
│   │   │   └── dashboard.py ← Stats, activity, revenue chart
│   │   ├── middleware/
│   │   │   └── auth.py      ← JWT verify + role guards
│   │   └── services/
│   │       └── axis_bank.py ← Axis Bank API (real + mock)
│   ├── alembic/             ← DB migrations
│   ├── Dockerfile
│   ├── requirements.txt
│   └── alembic.ini
├── frontend/
│   └── index.html           ← Full SPA — dynamic, role-based
├── docker-compose.yml
├── nginx.conf               ← Reverse proxy
├── .env                     ← All secrets (DO NOT commit)
└── README.md
```

---

## 🔐 Role Permission Matrix

| Feature                | Admin | Manager | Employee |
|------------------------|-------|---------|----------|
| Full Dashboard         | ✅    | ✅      | ✅ (limited) |
| Attendance (own)       | ✅    | ✅      | ✅       |
| Attendance (all staff) | ✅    | ✅      | ❌       |
| Leave Request          | ✅    | ✅      | ✅       |
| Leave Approval         | ✅    | ✅      | ❌       |
| View Projects          | ✅    | ✅      | ✅ (assigned) |
| Manage Projects/Tasks  | ✅    | ✅      | ❌       |
| Raise Payment Request  | ✅    | ✅      | ❌       |
| **Approve & Process Payment** | ✅ | ❌ | ❌ |
| Invoice Management     | ✅    | ✅      | ❌       |
| **User CRUD**          | ✅    | ❌      | ❌       |
| Payroll Disbursement   | ✅    | ❌      | ❌       |
| Bank Balance / Settings| ✅    | ❌      | ❌       |

---

## 🚀 Step-by-Step Execution

### Prerequisites
- Docker Desktop installed and running
- Git (optional)

### Step 1 — Clone / Extract project
```bash
# Extract the project zip or place files in a directory
cd os2-studio-ems
```

### Step 2 — Configure environment
```bash
# Copy and edit the .env file
cp .env .env.backup   # Keep a backup

# Edit .env — most important settings:
nano .env
```

Key variables to set:
```env
SECRET_KEY=your-64-char-random-secret-here      # Change this!
POSTGRES_PASSWORD=your-strong-password
AXIS_CLIENT_ID=your_axis_client_id              # Get from Axis Bank Dev Portal
AXIS_CLIENT_SECRET=your_axis_client_secret
AXIS_CORPORATE_ID=your_corporate_id
AXIS_ACCOUNT_NUMBER=9220000000001
SEED_DB=true                                    # Set false after first run
```

> **Note:** Without Axis Bank credentials, the system runs in **mock mode** — all payments simulate a 95% success rate. Perfect for development.

### Step 3 — Build and start all services
```bash
docker-compose up --build -d
```

This starts:
- `postgres` on port 5432
- `redis` on port 6379  
- `backend` (FastAPI) on port 8000
- `frontend` (nginx) on port 3000

### Step 4 — Wait for startup (~30 seconds)
```bash
# Monitor logs
docker-compose logs -f backend

# You should see:
# ✅ Database seeded successfully!
# INFO:     Application startup complete.
```

### Step 5 — Access the application
```
Frontend (UI):  http://localhost:3000
API Docs:       http://localhost:8000/docs
API Health:     http://localhost:8000/api/health
```

### Step 6 — Login
| Role     | Email                    | Password    |
|----------|--------------------------|-------------|
| Admin    | admin@os2studio.com      | admin123    |
| Manager  | rahul@os2studio.com      | manager123  |
| Employee | arun@os2studio.com       | emp123      |

---

## 🔧 Development Commands

```bash
# View all logs
docker-compose logs -f

# View backend logs only
docker-compose logs -f backend

# Restart backend after code changes
docker-compose restart backend

# Stop all services
docker-compose down

# Stop and remove all data (clean slate)
docker-compose down -v

# Run database migrations manually
docker-compose exec backend alembic upgrade head

# Access PostgreSQL
docker-compose exec postgres psql -U os2admin -d os2ems

# Access backend shell
docker-compose exec backend bash
```

---

## 🏦 Axis Bank Integration

### Getting Real Credentials
1. Register at https://developer.axisbank.com/
2. Create a Corporate Banking API application
3. Get Client ID, Client Secret, Corporate ID
4. Add your corporate account number
5. Update `.env` with real credentials
6. Restart backend: `docker-compose restart backend`

### APIs Used
- `POST /oauth2/token` — OAuth2 authentication
- `GET /corporate/banking/v1/balance` — Account balance
- `POST /corporate/banking/v1/fund-transfer/imps` — IMPS payment
- `POST /corporate/banking/v1/fund-transfer/neft` — NEFT payment
- `POST /corporate/banking/v1/fund-transfer/rtgs` — RTGS payment
- `POST /corporate/banking/v1/upi/collect` — UPI payment

### Payment Workflow
```
Manager raises request → Pending
Admin reviews → Approves → Axis Bank API called → Transaction logged
Admin reviews → Rejects → Request closed with reason
```

---

## 📊 Database Schema

Key tables:
- `users` — Login accounts with roles
- `employees` — Employee profiles (linked to users)
- `attendance` — Daily clock in/out records
- `leaves` — Leave requests + approvals
- `clients` — Client directory
- `projects` — Projects (M2M with employees)
- `tasks` — Kanban tasks per project
- `payrolls` — Monthly salary records
- `invoices` — Client billing
- `transactions` — Axis Bank payment records
- `payment_requests` — Manager-raised, admin-approved payments

---

## 🔄 API Endpoints Reference

```
AUTH
POST   /api/auth/login          Login
POST   /api/auth/refresh        Refresh token
GET    /api/auth/me             Current user

USERS (Admin only)
GET    /api/users               List users
POST   /api/users               Create user
PATCH  /api/users/{id}          Update user
DELETE /api/users/{id}          Delete user

EMPLOYEES
GET    /api/employees           List employees
POST   /api/employees           Add employee (Admin)
PATCH  /api/employees/{id}      Update employee
DELETE /api/employees/{id}      Soft delete

ATTENDANCE
GET    /api/attendance          List attendance
POST   /api/attendance/clock-in Clock in
POST   /api/attendance/clock-out Clock out
GET    /api/attendance/my-status Today's status
GET    /api/attendance/today-stats Summary

LEAVES
GET    /api/leaves              List leaves
POST   /api/leaves              Request leave
PATCH  /api/leaves/{id}/action  Approve/reject

PAYROLL
GET    /api/payroll             List payrolls
POST   /api/payroll/generate    Generate month
POST   /api/payroll/{id}/disburse Pay individual
POST   /api/payroll/bulk-disburse Bulk pay

INVOICES
GET    /api/invoices            List invoices
POST   /api/invoices            Create invoice
PATCH  /api/invoices/{id}       Update (mark paid)
DELETE /api/invoices/{id}       Delete

PAYMENTS
GET    /api/payments/requests   List requests
POST   /api/payments/requests   Raise request
POST   /api/payments/requests/{id}/action Approve/reject
GET    /api/payments/transactions List transactions
GET    /api/payments/balance    Bank balance

PROJECTS
GET    /api/projects            List projects
POST   /api/projects            Create project
PATCH  /api/projects/{id}       Update project
GET    /api/projects/tasks/all  All tasks
POST   /api/projects/{id}/tasks Add task
PATCH  /api/projects/tasks/{id} Update task (drag&drop)

DASHBOARD
GET    /api/dashboard/stats     KPI stats
GET    /api/dashboard/activity  Activity feed
GET    /api/dashboard/revenue-chart 6-month revenue
```

---

## 🛡️ Security Notes

1. **Change SECRET_KEY** in `.env` before production
2. **Change all default passwords** after first login
3. Set `SEED_DB=false` after first run
4. In production, restrict `CORS_ORIGINS` to your domain
5. Use HTTPS (add SSL to nginx config for production)
6. Keep `.env` out of version control (add to `.gitignore`)

---

## 🔧 Troubleshooting

**Backend won't start:**
```bash
docker-compose logs backend
# Common: wait for postgres healthcheck (up to 60s)
```

**Database connection error:**
```bash
docker-compose restart postgres
docker-compose restart backend
```

**Seed data not loaded:**
```bash
# Check SEED_DB=true in .env
docker-compose down -v   # Remove volumes
docker-compose up -d     # Fresh start
```

**Port conflicts:**
```bash
# Edit docker-compose.yml ports section
# Change "3000:80" to "3001:80" etc.
```
