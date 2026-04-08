from fastapi import APIRouter, UploadFile

from ...schemas.skill import FileContent, FileVersions, FileWriteRequest, SkillCreate, SkillDetail, SkillSummary
from ...services import skills as svc

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[SkillSummary])
def list_skills():
    return svc.list_skills()


@router.post("", response_model=SkillDetail, status_code=201)
def create_skill(body: SkillCreate):
    return svc.create_skill(body.name, body.description, body.create_scripts_folder)


@router.get("/{name}", response_model=SkillDetail)
def get_skill(name: str):
    return svc.get_skill(name)


@router.delete("/{name}", status_code=204)
def delete_skill(name: str):
    svc.delete_skill(name)


@router.get("/{name}/files/{path:path}/versions", response_model=FileVersions)
def file_versions(name: str, path: str):
    return svc.file_versions(f"{name}/{path}")


@router.get("/{name}/files/{path:path}", response_model=FileContent)
def read_file(name: str, path: str):
    return svc.read_file(name, path)


@router.put("/{name}/files/{path:path}", status_code=204)
def write_file(name: str, path: str, body: FileWriteRequest):
    svc.write_file(name, path, body.content)


@router.delete("/{name}/files/{path:path}", status_code=204)
def delete_file(name: str, path: str):
    svc.delete_file(name, path)


@router.post("/{name}/upload", status_code=201)
async def upload_file(name: str, file: UploadFile):
    data = await file.read()
    svc.upload_file(name, file.filename, data)
    return {"filename": file.filename}
