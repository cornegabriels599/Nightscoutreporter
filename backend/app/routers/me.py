from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.crypto import decrypt_token, encrypt_token
from app.db import get_db
from app.models import NightscoutConnection, User
from app.nightscout import fetch_status


router = APIRouter(prefix="/me", tags=["me"])


class NightscoutRequest(BaseModel):
    url: HttpUrl
    token: str


class NightscoutTestResponse(BaseModel):
    success: bool
    latency_ms: int
    sample_timestamp: str | None


@router.post("/nightscout")
def save_nightscout(
    payload: NightscoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    encrypted = encrypt_token(payload.token)
    existing = (
        db.query(NightscoutConnection).filter(NightscoutConnection.user_id == user.id).first()
    )
    if existing:
        existing.url = str(payload.url)
        existing.token_encrypted = encrypted
    else:
        db.add(
            NightscoutConnection(
                user_id=user.id,
                url=str(payload.url),
                token_encrypted=encrypted,
            )
        )
    db.commit()
    return {"success": True}


@router.get("/nightscout/test", response_model=NightscoutTestResponse)
def test_nightscout(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(NightscoutConnection).filter(NightscoutConnection.user_id == user.id).first()
    )
    if not connection:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nightscout not connected")

    token = decrypt_token(connection.token_encrypted)
    try:
        status_payload, latency_ms = fetch_status(connection.url, token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Nightscout unreachable") from exc

    timestamp = status_payload.get("time") or status_payload.get("serverTime") or None
    return NightscoutTestResponse(success=True, latency_ms=latency_ms, sample_timestamp=str(timestamp))
