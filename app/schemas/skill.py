from pydantic import BaseModel


class SkillMeta(BaseModel):
    name: str
    description: str = ""
    argument_hint: str = ""
    allowed_tools: list[str] = []
    mode: str = "automated"


class SkillSummary(BaseModel):
    name: str
    description: str = ""


class SkillDetail(BaseModel):
    meta: SkillMeta
    files: list[str]


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    create_scripts_folder: bool = False


class FileContent(BaseModel):
    content: str


class FileWriteRequest(BaseModel):
    content: str


class FileVersion(BaseModel):
    sha: str
    date: str
    message: str


class FileVersions(BaseModel):
    count: int
    versions: list[FileVersion]
