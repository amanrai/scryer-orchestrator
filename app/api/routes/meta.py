from fastapi import APIRouter

from ...schemas.process import HOOK_EVENT_NAMES

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/hook-events")
def get_hook_events():
    return {"hook_events": list(HOOK_EVENT_NAMES)}
