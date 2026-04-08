from fastapi import APIRouter

from .routes import events, hooks, messaging, meta, processes, skills, workflows

api_router = APIRouter()
api_router.include_router(events.router)
api_router.include_router(hooks.router)
api_router.include_router(messaging.router)
api_router.include_router(meta.router)
api_router.include_router(processes.router)
api_router.include_router(skills.router)
api_router.include_router(workflows.router)
