import tomllib

from app.core.root_path import get_project_root

_pyproject = get_project_root() / "pyproject.toml"
with open(_pyproject, "rb") as f:
    _version = tomllib.load(f)["project"]["version"]

APP_VERSION = f"v{_version}"
