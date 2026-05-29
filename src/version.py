import tomllib
from pathlib import Path

_pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
with open(_pyproject, "rb") as f:
    _version = tomllib.load(f)["project"]["version"]

APP_VERSION = f"v{_version}"
