from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...services import messaging as svc

router = APIRouter(prefix="/messaging", tags=["messaging"])


class RespondRequest(BaseModel):
    response: str


@router.get("/pending")
async def list_pending():
    return svc.list_pending()


@router.get("/{message_id}")
def get_message(message_id: str):
    msg = svc.get_message(message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail=f"Message not found: {message_id}")
    return msg


@router.post("/{message_id}/respond")
async def respond(message_id: str, body: RespondRequest):
    msg = svc.respond(message_id, body.response)
    if msg is None:
        raise HTTPException(status_code=404, detail=f"No pending message: {message_id}")
    return {"status": "ok", "message_id": message_id}
