from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
import uuid
from app.database import get_db
from app.models.models import Project, Task, Employee, Client, User, UserRole, ProjectStatus, TaskStatus, TrackerStatus
from app.schemas.schemas import ProjectCreate, ProjectUpdate, ProjectOut, TaskCreate, TaskUpdate, TaskOut
from app.middleware.auth import get_current_user, require_manager_or_admin

router = APIRouter(prefix="/api/projects", tags=["projects"])


async def _enrich_project(proj: Project, db: AsyncSession) -> ProjectOut:
    # Always refresh team eagerly BEFORE any attribute access — prevents MissingGreenlet
    await db.refresh(proj, ["team"])
    team_ids = [e.id for e in proj.team]
    team_names = [e.name for e in proj.team]

    client_name = None
    if proj.client_id:
        cl_result = await db.execute(select(Client).where(Client.id == proj.client_id))
        cl = cl_result.scalar_one_or_none()
        if cl:
            client_name = cl.name

    # Construct manually — never pass ORM object with relationships directly to model_validate
    return ProjectOut(
        id=proj.id,
        name=proj.name,
        client_id=proj.client_id,
        client_name=client_name,
        description=proj.description,
        document_url=proj.document_url,
        document_name=proj.document_name,
        start_date=proj.start_date,
        end_date=proj.end_date,
        value=proj.value,
        progress=proj.progress,
        status=proj.status,
        kanban_stage=proj.kanban_stage,
        team=team_ids,
        team_names=team_names,
        created_at=proj.created_at,
        asset_type=proj.asset_type,
        region=proj.region,
        asset_file_name=proj.asset_file_name,
        expected_date=proj.expected_date,
        completion_date_design=proj.completion_date_design,
        project_lead=proj.project_lead,
        asset_content_url=proj.asset_content_url,
        tracker_status=proj.tracker_status,
        sample_documents=proj.sample_documents,
        feedback_revision=proj.feedback_revision,
        design_url=proj.design_url,
    )


@router.get("", response_model=List[ProjectOut])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # Use selectinload to eagerly fetch team in one JOIN — zero lazy loads
    result = await db.execute(
        select(Project).options(selectinload(Project.team)).order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    # Employee sees only their assigned projects
    if current.role == UserRole.employee:
        emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
        emp = emp_result.scalar_one_or_none()
        if emp:
            projects = [p for p in projects if any(e.id == emp.id for e in p.team)]
        else:
            projects = []
    return [await _enrich_project(p, db) for p in projects]


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    proj = Project(
        id="P" + uuid.uuid4().hex[:6].upper(),
        name=data.name,
        client_id=data.client_id,
        description=data.description,
        document_url=data.document_url,
        document_name=data.document_name,
        start_date=data.start_date,
        end_date=data.end_date,
        value=data.value,
        asset_type=data.asset_type,
        region=data.region,
        asset_file_name=data.asset_file_name,
        expected_date=data.expected_date,
        completion_date_design=data.completion_date_design,
        project_lead=data.project_lead,
        asset_content_url=data.asset_content_url,
        tracker_status=data.tracker_status or TrackerStatus.inprogress,
        sample_documents=data.sample_documents,
        feedback_revision=data.feedback_revision,
        design_url=data.design_url,
    )
    db.add(proj)
    await db.flush()
    if data.team_ids:
        emp_result = await db.execute(select(Employee).where(Employee.id.in_(data.team_ids)))
        employees = emp_result.scalars().all()
        await db.refresh(proj, ['team'])  # prevent MissingGreenlet on new object
        proj.team = employees
        await db.flush()
    return await _enrich_project(proj, db)


@router.get("/{proj_id}", response_model=ProjectOut)
async def get_project(proj_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(
        select(Project).options(selectinload(Project.team)).where(Project.id == proj_id)
    )
    proj = result.scalar_one_or_none()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return await _enrich_project(proj, db)


@router.patch("/{proj_id}", response_model=ProjectOut)
async def update_project(
    proj_id: str,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Project).options(selectinload(Project.team)).where(Project.id == proj_id)
    )
    proj = result.scalar_one_or_none()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    if current.role == UserRole.employee:
        # Employees can only update progress on projects they are assigned to
        emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
        emp = emp_result.scalar_one_or_none()
        if not emp or not any(e.id == emp.id for e in proj.team):
            raise HTTPException(status_code=403, detail="You are not a team member of this project")
        # Employees may change the tracker Status, Completion Date (Design), and Design URL —
        # everything else on the tracker row is admin/manager-managed
        if data.tracker_status is not None:
            proj.tracker_status = data.tracker_status
            if data.tracker_status == TrackerStatus.completed:
                proj.progress = 100
                proj.status = ProjectStatus.completed
        if data.completion_date_design is not None:
            proj.completion_date_design = data.completion_date_design
        if data.design_url is not None:
            proj.design_url = data.design_url
    else:
        # Manager / Admin: full update
        for field, value in data.model_dump(exclude_none=True, exclude={"team_ids"}).items():
            setattr(proj, field, value)
        if data.tracker_status == TrackerStatus.completed:
            proj.progress = 100
            proj.status = ProjectStatus.completed
        if data.team_ids is not None:
            emp_result = await db.execute(select(Employee).where(Employee.id.in_(data.team_ids)))
            employees = emp_result.scalars().all()
            await db.refresh(proj, ['team'])
            proj.team = employees
            await db.flush()

    await db.flush()
    return await _enrich_project(proj, db)


@router.delete("/{proj_id}", status_code=204)
async def delete_project(proj_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_manager_or_admin)):
    result = await db.execute(select(Project).where(Project.id == proj_id))
    proj = result.scalar_one_or_none()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(proj)


# ── Tasks ──────────────────────────────────────────────────────────────────────

@router.get("/tasks/all", response_model=List[TaskOut])
async def list_all_tasks(
    project_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    query = select(Task)
    if project_id:
        query = query.where(Task.project_id == project_id)
    if current.role == UserRole.employee:
        emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
        emp = emp_result.scalar_one_or_none()
        if emp:
            query = query.where(Task.assigned_to == emp.id)
        else:
            return []
    result = await db.execute(query.order_by(Task.created_at.desc()))
    tasks = result.scalars().all()
    return [await _enrich_task(t, db) for t in tasks]


async def _enrich_task(task: Task, db: AsyncSession) -> TaskOut:
    out = TaskOut.model_validate(task)
    if task.project_id:
        proj_result = await db.execute(select(Project).where(Project.id == task.project_id))
        proj = proj_result.scalar_one_or_none()
        if proj:
            out.project_name = proj.name
    if task.assigned_to:
        emp_result = await db.execute(select(Employee).where(Employee.id == task.assigned_to))
        emp = emp_result.scalar_one_or_none()
        if emp:
            out.assignee_name = emp.name
    return out


@router.post("/{proj_id}/tasks", response_model=TaskOut, status_code=201)
async def create_task(
    proj_id: str,
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    task = Task(
        id="T" + uuid.uuid4().hex[:7].upper(),
        project_id=proj_id,
        title=data.title,
        description=data.description,
        assigned_to=data.assigned_to,
        priority=data.priority,
        status=data.status,
        due_date=data.due_date,
    )
    db.add(task)
    await db.flush()
    return await _enrich_task(task, db)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if current.role == UserRole.employee:
        # Employees can only update status on tasks assigned to THEM
        emp_result = await db.execute(select(Employee).where(Employee.user_id == current.id))
        emp = emp_result.scalar_one_or_none()
        if not emp or task.assigned_to != emp.id:
            raise HTTPException(status_code=403, detail="You can only update tasks assigned to you")
        if data.status is not None:
            task.status = data.status
    else:
        # Manager / Admin: full update
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(task, field, value)

    await db.flush()

    # Auto-set project progress to 100% when a task moves to "review" (work complete, awaiting sign-off)
    if data.status in ("review", "done") and task.project_id:
        proj_result = await db.execute(select(Project).where(Project.id == task.project_id))
        proj = proj_result.scalar_one_or_none()
        if proj and proj.progress < 100:
            proj.progress = 100
            if data.status == "done":
                proj.status = ProjectStatus.completed
            await db.flush()

    return await _enrich_task(task, db)


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_manager_or_admin)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(task)
