from __future__ import annotations

from uuid import UUID

from fastapi import WebSocket
from jose import ExpiredSignatureError, JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.users.models import User
from app.apis.users.repository import UserRepository
from app.core.database.base import UserId
from app.iam.token_service import TokenService


def _extract_token(websocket: WebSocket) -> str | None:
    # 1) Authorization: Bearer <token>
    auth = websocket.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()

    # 2) Cookie (if your UI stores it there)
    # token = websocket.cookies.get("access_token")
    # if token: return token

    # 3) Query param fallback (useful for browsers)
    token = websocket.query_params.get("token")
    if token:
        return token.strip()

    return None


async def get_current_user_ws(
    websocket: WebSocket, session: AsyncSession
) -> User | None:
    token = _extract_token(websocket)
    if not token:
        # 4401 is commonly used by WS stacks; FastAPI uses HTTPException only for HTTP.
        await websocket.close(code=4401)
        return None

    try:
        claims = TokenService.decode_token(token)
    except ExpiredSignatureError:
        await websocket.close(code=4401)
        return None
    except JWTError:
        await websocket.close(code=4401)
        return None
    except Exception:
        await websocket.close(code=4401)
        return None

    if isinstance(claims, dict):
        user_id = claims.get("sub") or claims.get("user_id")
    else:
        user_id = getattr(claims, "user_id", None) or getattr(claims, "sub", None)
    if not user_id:
        await websocket.close(code=4401)
        return None

    try:
        user_uuid = UUID(str(user_id))
    except (TypeError, ValueError):
        await websocket.close(code=4401)
        return None

    repo = UserRepository(session)
    user = await repo.get_by_id(UserId(user_uuid))
    if not user:
        await websocket.close(code=4401)
        return None
    if not user.is_active:
        await websocket.close(code=4401)
        return None

    return user
