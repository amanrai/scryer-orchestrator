class WorkflowNotFoundError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Workflow not found: {name}")


class WorkflowAlreadyExistsError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Workflow already exists: {name}")


class InvalidStepReferenceError(Exception):
    def __init__(self, names: list[str]) -> None:
        super().__init__(f"Unknown step assets referenced in workflow: {', '.join(names)}")


class PathTraversalError(Exception):
    def __init__(self, path: str) -> None:
        super().__init__(f"Path traversal blocked: {path}")


class SkillNotFoundError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Skill not found: {name}")


class SkillAlreadyExistsError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Skill already exists: {name}")


class FileNotFoundInSkillError(Exception):
    def __init__(self, skill: str, path: str) -> None:
        super().__init__(f"File not found in skill {skill}: {path}")
