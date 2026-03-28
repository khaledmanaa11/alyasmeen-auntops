"""broadcast.py — Broadcast messaging router.

Endpoints:
    POST /broadcast/improve  — AI tone/grammar improvement for a draft message
    POST /broadcast/send     — Send broadcast to a customer segment
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, validator

from app.services.ai_service import improve_message

router = APIRouter(prefix="/broadcast", tags=["broadcast"])


class ImproveRequest(BaseModel):
    message: str

    @validator("message")
    def message_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be empty")
        if len(v) > 2000:
            raise ValueError("message must be 2000 characters or fewer")
        return v


@router.post("/improve")
async def improve_broadcast_message(body: ImproveRequest) -> dict:
    """
    Accept a draft broadcast message and return an AI-improved version.

    Body:   {"message": "..."}
    Return: {"original": "...", "improved": "...", "language": "ar"|"en"}
    """
    try:
        return improve_message(body.message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI improvement failed: {exc}")
