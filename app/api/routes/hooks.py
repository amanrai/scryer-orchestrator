from fastapi import APIRouter, HTTPException

from ...schemas.hook import HookCreate, HookDetail, HookSummary, HookUpdate
from ...services import hook_assets as svc

router = APIRouter(prefix="/hooks", tags=["hooks"])


@router.get("", response_model=list[HookSummary])
def list_hooks():
    return svc.list_hooks()


@router.post("", response_model=HookDetail, status_code=201)
def create_hook(body: HookCreate):
    try:
        return svc.create_hook(body.name, body.content)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{name}", response_model=HookDetail)
def get_hook(name: str):
    try:
        return svc.get_hook(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{name}", response_model=HookDetail)
def update_hook(name: str, body: HookUpdate):
    try:
        return svc.update_hook(name, body.content)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{name}", status_code=204)
def delete_hook(name: str):
    try:
        svc.delete_hook(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return None
