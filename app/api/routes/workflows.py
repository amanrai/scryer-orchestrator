from fastapi import APIRouter

from ...schemas.workflow import WorkflowCreate, WorkflowDetail, WorkflowSummary, WorkflowUpdate
from ...services import workflows as svc

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowSummary])
def list_workflows():
    return svc.list_workflows()


@router.post("", response_model=WorkflowDetail)
def create_workflow(body: WorkflowCreate):
    return svc.create_workflow(body.name, body.description, body.phases, body.hooks)


@router.get("/{name}", response_model=WorkflowDetail)
def get_workflow(name: str):
    return svc.get_workflow(name)


@router.put("/{name}", response_model=WorkflowDetail)
def update_workflow(name: str, body: WorkflowUpdate):
    return svc.update_workflow(name, body.description, body.phases, body.hooks)
