from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from jose import JWTError, jwt

from app.config import settings
from app.database import get_db, AsyncSessionLocal
from app.models.models import ChatMessage, ChatReadStatus, User
from app.schemas.schemas import ChatMessageOut, ChatUnreadOut
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── REST: history + read status ─────────────────────────────────────────────────

@router.get("/messages", response_model=List[ChatMessageOut])
async def get_messages(
    before_id: Optional[int] = Query(default=None),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    _current: User = Depends(get_current_user),
):
    query = select(ChatMessage).order_by(ChatMessage.id.desc())
    if before_id:
        query = query.where(ChatMessage.id < before_id)
    query = query.limit(limit)
    result = await db.execute(query)
    rows = list(result.scalars().all())
    rows.reverse()  # return oldest-first for easy rendering
    return rows


@router.get("/unread", response_model=ChatUnreadOut)
async def get_unread(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    last_id_result = await db.execute(select(func.max(ChatMessage.id)))
    last_id = last_id_result.scalar() or 0

    read_result = await db.execute(select(ChatReadStatus).where(ChatReadStatus.user_id == current.id))
    read_row = read_result.scalar_one_or_none()
    last_read = read_row.last_read_message_id if read_row else 0

    if last_id <= last_read:
        return {"unread_count": 0, "last_message_id": last_id}

    count_result = await db.execute(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.id > last_read, ChatMessage.sender_id != current.id
        )
    )
    unread = count_result.scalar() or 0
    return {"unread_count": unread, "last_message_id": last_id}


@router.post("/read", status_code=200)
async def mark_read(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    last_id_result = await db.execute(select(func.max(ChatMessage.id)))
    last_id = last_id_result.scalar() or 0

    result = await db.execute(select(ChatReadStatus).where(ChatReadStatus.user_id == current.id))
    row = result.scalar_one_or_none()
    if row:
        row.last_read_message_id = last_id
    else:
        db.add(ChatReadStatus(user_id=current.id, last_read_message_id=last_id))
    await db.flush()
    return {"message": "ok", "last_read_message_id": last_id}


# ── WebSocket: live broadcast ────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, payload: dict):
        dead = []
        for conn in self.active:
            try:
                await conn.send_json(payload)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.disconnect(d)


manager = ConnectionManager()


async def _authenticate_ws_token(token: str) -> Optional[User]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        token_type = payload.get("type")
        if user_id is None or token_type != "access":
            return None
    except JWTError:
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            return None
        return user


@router.websocket("/ws")
async def chat_ws(websocket: WebSocket, token: str = Query(...)):
    user = await _authenticate_ws_token(token)
    if not user:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            text = (data.get("message") or "").strip()
            if not text:
                continue
            text = text[:2000]  # sane cap

            async with AsyncSessionLocal() as db:
                msg = ChatMessage(
                    sender_id=user.id,
                    sender_name=user.name,
                    sender_role=user.role.value if hasattr(user.role, "value") else str(user.role),
                    message=text,
                )
                db.add(msg)
                await db.commit()
                await db.refresh(msg)

            await manager.broadcast({
                "type": "message",
                "id": msg.id,
                "sender_id": msg.sender_id,
                "sender_name": msg.sender_name,
                "sender_role": msg.sender_role,
                "message": msg.message,
                "created_at": msg.created_at.isoformat(),
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
