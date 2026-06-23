from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root() / path
