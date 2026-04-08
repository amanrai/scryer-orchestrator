from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from ...schemas.process import (
    NotificationEvent,
    WorkflowInstanceCreate,
    WorkflowInstanceRead,
    WorkflowInstanceSummary,
    WorkflowPhaseInsert,
    WorkflowStepConfigUpdate,
    WorkflowStepInsert,
    WorkflowStepMove,
    WorkflowStepTarget,
)
from ...services import processes

router = APIRouter(prefix="/processes", tags=["processes"])


@router.post("", response_model=WorkflowInstanceRead, status_code=201)
async def create_process(body: WorkflowInstanceCreate):
    instance = await processes.create_workflow_instance(body)
    return await processes.start_workflow_instance(instance.workflow_uuid)


@router.get("", response_model=list[WorkflowInstanceSummary])
async def list_processes():
    return await processes.list_workflow_instances()


@router.get("/{workflow_uuid}", response_model=WorkflowInstanceRead)
async def get_process(workflow_uuid: str):
    instance = await processes.get_workflow_instance(workflow_uuid)
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow instance not found: {workflow_uuid}")
    return instance


@router.get("/{workflow_uuid}/logs", response_class=PlainTextResponse)
async def get_process_logs(workflow_uuid: str):
    content = await processes.read_workflow_log(workflow_uuid)
    if content is None:
        raise HTTPException(status_code=404, detail=f"Workflow instance not found: {workflow_uuid}")
    return content


@router.delete("/{workflow_uuid}", status_code=204)
async def delete_process(workflow_uuid: str):
    deleted = await processes.delete_workflow_instance(workflow_uuid)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Workflow instance not found: {workflow_uuid}")
    return None


@router.post("/{workflow_uuid}/pause", response_model=WorkflowInstanceRead)
async def pause_process(workflow_uuid: str):
    instance = await processes.pause_workflow_instance(workflow_uuid)
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow instance not found: {workflow_uuid}")
    return instance


@router.post("/{workflow_uuid}/resume", response_model=WorkflowInstanceRead)
async def resume_process(workflow_uuid: str):
    instance = await processes.resume_workflow_instance(workflow_uuid)
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow instance not found: {workflow_uuid}")
    return instance


@router.patch("/{workflow_uuid}/steps/config", response_model=WorkflowInstanceRead)
async def update_step_config(workflow_uuid: str, body: WorkflowStepConfigUpdate):
    try:
        instance = await processes.update_step_config(workflow_uuid, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow instance not found: {workflow_uuid}")
    return instance


@router.post("/{workflow_uuid}/phases", response_model=WorkflowInstanceRead)
async def add_phase(workflow_uuid: str, body: WorkflowPhaseInsert):
    try:
        instance = await processes.add_phase(workflow_uuid, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow instance not found: {workflow_uuid}")
    return instance


@router.delete("/{workflow_uuid}/phases/{phase_number}", response_model=WorkflowInstanceRead)
async def delete_phase(workflow_uuid: str, phase_number: int):
    try:
        instance = await processes.delete_phase(workflow_uuid, phase_number)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow instance not found: {workflow_uuid}")
    return instance


@router.post("/{workflow_uuid}/steps", response_model=WorkflowInstanceRead)
async def add_step(workflow_uuid: str, body: WorkflowStepInsert):
    try:
        instance = await processes.add_step(workflow_uuid, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow instance not found: {workflow_uuid}")
    return instance


@router.delete("/{workflow_uuid}/steps", response_model=WorkflowInstanceRead)
async def delete_step(workflow_uuid: str, body: WorkflowStepTarget):
    try:
        instance = await processes.delete_step(workflow_uuid, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow instance not found: {workflow_uuid}")
    return instance


@router.post("/{workflow_uuid}/steps/move", response_model=WorkflowInstanceRead)
async def move_step(workflow_uuid: str, body: WorkflowStepMove):
    try:
        instance = await processes.move_step(workflow_uuid, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow instance not found: {workflow_uuid}")
    return instance


@router.post("/{workflow_uuid}/steps/run", response_model=WorkflowInstanceRead)
async def run_step(workflow_uuid: str, body: WorkflowStepTarget):
    try:
        instance = await processes.run_step(workflow_uuid, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow instance not found: {workflow_uuid}")
    return instance


@router.post("/{workflow_uuid}/steps/kill", response_model=WorkflowInstanceRead)
async def kill_step(workflow_uuid: str, body: WorkflowStepTarget):
    try:
        instance = await processes.kill_step(workflow_uuid, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Workflow instance not found: {workflow_uuid}")
    return instance


@router.post("/notify", status_code=200)
async def notify(event: NotificationEvent):
    await processes.handle_notification(event)
    return {"ok": True}
