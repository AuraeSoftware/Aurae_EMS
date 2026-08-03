from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import uuid
from app.database import get_db
from app.models.models import Client
from app.schemas.schemas import ClientCreate, ClientUpdate, ClientOut
from app.middleware.auth import get_current_user, require_manager_or_admin

router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.get("", response_model=List[ClientOut])
async def list_clients(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Client).where(Client.is_active == True).order_by(Client.name))
    return [ClientOut.model_validate(c) for c in result.scalars().all()]


@router.post("", response_model=ClientOut, status_code=201)
async def create_client(
    data: ClientCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    client = Client(
        id="C" + uuid.uuid4().hex[:6].upper(),
        **data.model_dump(),
    )
    db.add(client)
    await db.flush()
    return ClientOut.model_validate(client)


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(client_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return ClientOut.model_validate(client)


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: str,
    data: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(client, field, value)
    await db.flush()
    return ClientOut.model_validate(client)


@router.delete("/{client_id}", status_code=204)
async def delete_client(client_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_manager_or_admin)):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    client.is_active = False
    await db.flush()
