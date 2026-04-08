import asyncio
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.router import api_router
from .config import settings
from .services.event_log import close as close_event_log
from .services.git import ensure_repo
from .services.messaging import close as close_messaging
from .services.messaging import consume_stream
from .services.notifications import run_timeout_checker
from .services.runtime import ensure_runtime_roots

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)


class SuppressProcessPollingAccessFilter(logging.Filter):
    _process_detail_pattern = re.compile(r'GET /processes/[^"\s]+ HTTP/')

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if 'GET /processes HTTP/' in message:
            return False
        if self._process_detail_pattern.search(message):
            return False
        return True


for handler in logging.getLogger("uvicorn.access").handlers:
    handler.addFilter(SuppressProcessPollingAccessFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    for root in settings.skills_paths:
        ensure_repo(root)
    ensure_repo(settings.workflows_path)
    ensure_repo(settings.hooks_path)
    ensure_runtime_roots()
    bg_tasks = [
        asyncio.create_task(consume_stream()),
        asyncio.create_task(run_timeout_checker()),
    ]
    yield
    for task in bg_tasks:
        task.cancel()
    await close_messaging()
    close_event_log()


app = FastAPI(title="Scryer New Orchestrator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
